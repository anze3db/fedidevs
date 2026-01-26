import logging

from django.utils.translation import gettext as _
from mastodon import (
    Mastodon,
    MastodonAPIError,
    MastodonBadGatewayError,
    MastodonError,
    MastodonInternalServerError,
    MastodonNetworkError,
    MastodonNotFoundError,
    MastodonServiceUnavailableError,
    MastodonUnauthorizedError,
    MastodonVersionError,
)

logger = logging.getLogger(__name__)


class FollowError(Exception):
    """Exception raised when account resolution or follow operation fails."""

    pass


def resolve_and_follow_account(mastodon: Mastodon, account, instance):
    """
    Resolve an account on a specific Mastodon instance and follow it.

    Args:
        mastodon: Mastodon API client instance
        account: Account object with username_at_instance, instance, account_id, url attributes
        instance: Instance object with url attribute

    Raises:
        FollowError: If account resolution or follow operation fails
    """
    # Determine the account ID to follow
    if account.instance == instance.url:
        account_id = account.account_id
    else:
        try:
            local_account = mastodon.account_lookup(acct=account.username_at_instance)
        except (MastodonNotFoundError, MastodonVersionError, MastodonInternalServerError) as e:
            # Attempt to resolve through search:
            try:
                local_accounts = mastodon.account_search(q=account.username_at_instance, resolve=True, limit=1)
            except MastodonServiceUnavailableError as inner_e:
                logger.info("Service unavailable when searching for %s", account.username_at_instance)
                raise FollowError(_("Service unavailable")) from inner_e
            except Exception as inner_e:
                logger.info("Unknown error when searching for %s", account.username_at_instance)
                raise FollowError(_("Unknown error")) from inner_e
            if not local_accounts:
                logger.info("Account not found on instance %s", account.username_at_instance)
                raise FollowError(_("Account not found on instance")) from e
            local_account = local_accounts[0]
            if local_account["acct"].lower() != account.username_at_instance[1:]:
                logger.info(
                    "Account mismatch %s %s",
                    account.username_at_instance[1:],
                    local_account["acct"],
                )
                raise FollowError(_("Account not found")) from e
        except MastodonUnauthorizedError as e:
            logger.info("Not authorized %s", account.username_at_instance)
            raise FollowError(_("Not Authorized")) from e
        except MastodonNetworkError as e:
            logger.info("Network error when looking up %s", account.username_at_instance)
            raise FollowError(_("Network error")) from e
        except MastodonAPIError as e:
            logger.info("Unknown error when looking up %s", account.username_at_instance)
            raise FollowError(_("Failed to follow")) from e
        except MastodonError as e:
            logger.info("Unknown error when looking up %s", account.username_at_instance)
            raise FollowError(_("Failed to follow")) from e
        account_id = local_account["id"]

    # Follow the account
    try:
        mastodon.account_follow(account_id)
    except MastodonUnauthorizedError as e:
        raise FollowError(_("Unauthorized")) from e
    except MastodonNotFoundError as e:
        raise FollowError(_("Account not found")) from e
    except MastodonNetworkError as e:
        logger.info("Network error when following %s", account.username_at_instance)
        raise FollowError(_("Network error")) from e
    except MastodonError as e:
        # We weren't able to follow the user. Maybe the account was moved?
        try:
            local_account = mastodon.account_lookup(acct=account.username_at_instance)
        except MastodonNotFoundError as inner_e:
            logger.info("Account not found on instance %s", account.username_at_instance)
            raise FollowError(_("Account not found")) from inner_e
        except MastodonBadGatewayError as inner_e:
            logger.info("Bad gateway when checking moved for %s", account.username_at_instance)
            raise FollowError(
                _("Mastodon instance responded with a bad gateway error, please try again later")
            ) from inner_e
        except MastodonError as inner_e:
            logger.info("Unknown error when checking moved for %s", account.username_at_instance)
            raise FollowError(_("Failed to follow")) from inner_e
        if moved := local_account.get("moved"):
            account.moved = moved
            account.save(update_fields=("moved",))
            logger.info("Account %s moved", account.username_at_instance)
            raise FollowError(_("Account has moved")) from e

        logger.info("Unknown error when following %s", account.username_at_instance)
        raise FollowError(_("Failed to follow")) from e
