import datetime
from unittest.mock import Mock, patch

import httpx
from ddt import data, ddt, unpack
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from accounts.models import Account
from starter_packs.models import MAX_OWNERS, MAX_PINNED_ACCOUNTS, StarterPackAccount, StarterPackInvitation
from starter_packs.remote_follow import get_subscribe_url, parse_handle


class TestStarterPacks(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("starter_packs.StarterPack", _quantity=5)

    def test_index_page(self):
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Community Starter Packs")
        self.assertContains(response, "Your Starter Packs")
        self.assertContains(response, "Starter Packs Containing You")

    def test_index_page_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Community Starter Packs")
        self.assertContains(response, "Your Starter Packs")
        self.assertContains(response, "Starter Packs Containing You")

    def test_index_page_with_own_starter_packs(self):
        for pack in baker.make("starter_packs.StarterPack", created_by=self.user, _quantity=2):
            pack.owners.add(self.user)
        self.client.force_login(self.user)
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Starter Packs")
        self.assertContains(response, "Your Starter Packs")
        self.assertContains(response, "Starter Packs Containing You")

    def test_index_page_language_filter(self):
        french_pack = baker.make(
            "starter_packs.StarterPack", title="Francophones", languages=["fr", "en"], published_at=timezone.now()
        )
        german_pack = baker.make(
            "starter_packs.StarterPack", title="Deutschsprachige", languages=["de"], published_at=timezone.now()
        )
        response = self.client.get(reverse("starter_packs"), {"language": "fr"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, french_pack.title)
        self.assertNotContains(response, german_pack.title)

    def test_language_filter_only_lists_used_languages(self):
        baker.make("starter_packs.StarterPack", languages=["fr"], published_at=timezone.now())
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        # French is used by a published pack and appears as a filter option; German
        # is not used, so it has no option. (The site locale switcher also has
        # value="de" buttons, so we match the <option> specifically.)
        self.assertContains(response, '<option value="fr"')
        self.assertNotContains(response, '<option value="de"')

    def test_index_page_unknown_language_ignored(self):
        pack = baker.make(
            "starter_packs.StarterPack", title="Francophones", languages=["fr"], published_at=timezone.now()
        )
        response = self.client.get(reverse("starter_packs"), {"language": "not-a-language"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pack.title)


class TestCreateStarterPack(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)

    def test_create_page(self):
        response = self.client.get(reverse("create_starter_pack"))
        self.assertRedirects(response, reverse("login") + "?next=/starter-packs/create/")

    def test_create_page_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("create_starter_pack"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mastodon starter packs")
        # The language picker and its filter box render, including languages from
        # the expanded list.
        self.assertContains(response, 'id="language-filter"')
        self.assertContains(response, "🇰🇪 Swahili")
        # Uncommon languages are collapsed behind "Show more" by default (rendered
        # as hidden extras, so no expanded extra chip is present).
        self.assertContains(response, "Show more languages")
        self.assertNotContains(response, "language-extra inline-flex")

    def test_create_starter_pack(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("create_starter_pack"),
            {
                "title": "Test Starter Pack",
                "description": "This is a test starter pack",
            },
        )
        starter_pack = self.user.starterpack_set.first()
        self.assertEqual(starter_pack.created_by, self.user)
        # The creator is automatically the first owner.
        self.assertTrue(starter_pack.owners.filter(pk=self.user.pk).exists())
        self.assertRedirects(response, reverse("edit_accounts_starter_pack", args=[starter_pack.slug]))

    def test_form_error(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("create_starter_pack"), {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertEqual(self.user.starterpack_set.count(), 0)

    def test_create_starter_pack_with_languages(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("create_starter_pack"),
            {
                "title": "Multilingual Pack",
                "description": "People to follow",
                "languages": ["fr", "de"],
            },
        )
        starter_pack = self.user.starterpack_set.first()
        self.assertCountEqual(starter_pack.languages, ["fr", "de"])

    def test_create_starter_pack_defaults_to_no_languages(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("create_starter_pack"),
            {
                "title": "Test Starter Pack",
                "description": "This is a test starter pack",
            },
        )
        starter_pack = self.user.starterpack_set.first()
        self.assertEqual(starter_pack.languages, [])

    def test_create_starter_pack_rejects_unknown_language(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("create_starter_pack"),
            {
                "title": "Test Starter Pack",
                "description": "This is a test starter pack",
                "languages": ["not-a-language"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.user.starterpack_set.count(), 0)

    def test_create_starter_pack_rejects_too_many_languages(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("create_starter_pack"),
            {
                "title": "Test Starter Pack",
                "description": "This is a test starter pack",
                "languages": ["en", "fr", "de", "es", "it", "pt"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "up to 5 languages")
        self.assertEqual(self.user.starterpack_set.count(), 0)


class TestEditStarterPack(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user)
        cls.starter_pack.owners.add(cls.user)

    def test_not_logged_in(self):
        response = self.client.get(reverse("edit_starter_pack", args=[self.starter_pack.slug]))
        self.assertRedirects(response, reverse("login") + f"?next=/starter-packs/{self.starter_pack.slug}/edit/")

    def test_not_owned_starter_pack(self):
        other_user = baker.make("auth.User")
        self.client.force_login(other_user)
        response = self.client.get(reverse("edit_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 404)

    def test_edit_starter_packs(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("edit_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mastodon starter packs")
        self.assertContains(response, self.starter_pack.title)
        self.assertContains(response, self.starter_pack.description)

    def test_edit_starter_pack_post(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("edit_starter_pack", args=[self.starter_pack.slug]),
            {
                "title": "New title",
                "description": "New description",
            },
        )
        self.starter_pack.refresh_from_db()
        self.assertEqual(self.starter_pack.title, "New title")
        self.assertEqual(self.starter_pack.description, "New description")
        self.assertRedirects(response, reverse("edit_accounts_starter_pack", args=[self.starter_pack.slug]))

    def test_edit_shows_selected_uncommon_language_expanded(self):
        # Japanese is not a common language, but a pack tagged with it must show it
        # by default (as a visible extra, not hidden behind "Show more").
        self.starter_pack.languages = ["ja"]
        self.starter_pack.save(update_fields=["languages"])
        self.client.force_login(self.user)
        response = self.client.get(reverse("edit_starter_pack", args=[self.starter_pack.slug]))
        self.assertContains(response, "language-extra inline-flex")

    def test_edit_starter_pack_languages(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("edit_starter_pack", args=[self.starter_pack.slug]),
            {
                "title": "New title",
                "description": "New description",
                "languages": ["de", "fr"],
            },
        )
        self.starter_pack.refresh_from_db()
        self.assertCountEqual(self.starter_pack.languages, ["de", "fr"])


class TestEditStarterPackAccounts(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user)
        cls.starter_pack.owners.add(cls.user)

    def test_not_logged_in(self):
        response = self.client.get(reverse("edit_accounts_starter_pack", args=[self.starter_pack.slug]))
        self.assertRedirects(
            response, reverse("login") + f"?next=/starter-packs/{self.starter_pack.slug}/edit/accounts/"
        )

    def test_not_owned_starter_pack(self):
        other_user = baker.make("auth.User")
        self.client.force_login(other_user)
        response = self.client.get(reverse("edit_accounts_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 404)

    def test_edit_starter_packs(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("edit_accounts_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search @username@instance.org")


class TestAddAccountsSearch(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user)
        cls.starter_pack.owners.add(cls.user)
        cls.instance = baker.make("accounts.Instance", instance="instance.org")
        cls.account = baker.make(
            "accounts.Account",
            username="testuser",
            username_at_instance="testuser@instance.org",
            discoverable=True,
            instance_model=cls.instance,
        )

    @patch("starter_packs.views.crawlone")
    def test_username_search_shows_checked_for_existing_account(self, mock_crawlone):
        """When searching by username for an account already in the pack, checkbox should be checked."""
        mock_crawlone.return_value = self.account
        baker.make(
            "starter_packs.StarterPackAccount",
            starter_pack=self.starter_pack,
            account=self.account,
        )
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("edit_accounts_starter_pack", args=[self.starter_pack.slug]),
            {"q": "testuser@instance.org"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'checked="checked"')

    @patch("starter_packs.views.crawlone")
    def test_username_search_shows_unchecked_for_new_account(self, mock_crawlone):
        """When searching by username for an account not in the pack, checkbox should be unchecked."""
        mock_crawlone.return_value = self.account
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("edit_accounts_starter_pack", args=[self.starter_pack.slug]),
            {"q": "testuser@instance.org"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'checked="checked"')


class TestDeleteStarterPack(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user)
        cls.starter_pack.owners.add(cls.user)

    def test_not_logged_in(self):
        response = self.client.get(reverse("delete_starter_pack", args=[self.starter_pack.slug]))
        self.assertRedirects(response, reverse("login") + f"?next=/starter-packs/{self.starter_pack.slug}/delete/")

    def test_not_owned_starter_pack(self):
        other_user = baker.make("auth.User")
        self.client.force_login(other_user)
        response = self.client.get(reverse("delete_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 404)

    def test_delete_confirmation(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("delete_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, f'Are you sure you want to delete the starter pack <strong>"{self.starter_pack.title}"</strong>?'
        )

    def test_delete(self):
        self.client.force_login(self.user)
        self.assertIsNone(self.starter_pack.deleted_at)
        response = self.client.post(reverse("delete_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 302)
        self.starter_pack.refresh_from_db()
        self.assertIsNotNone(self.starter_pack.deleted_at)


class TestToggleStarterPackAccount(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.user)
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user)
        cls.starter_pack.owners.add(cls.user)

    def test_add_account(self):
        account = baker.make("accounts.Account", discoverable=True)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "toggle_account_to_starter_pack",
                kwargs={"starter_pack_slug": self.starter_pack.slug, "account_id": account.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            StarterPackAccount.objects.filter(
                account_id=account.id, starter_pack_id=self.starter_pack.id, created_by=self.user
            ).exists()
        )

    def test_remove_account(self):
        account = baker.make("accounts.Account", discoverable=True)
        self.client.force_login(self.user)
        baker.make("starter_packs.StarterPackAccount", account=account, starter_pack=self.starter_pack)
        response = self.client.post(
            reverse(
                "toggle_account_to_starter_pack",
                kwargs={"starter_pack_slug": self.starter_pack.slug, "account_id": account.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            StarterPackAccount.objects.filter(account_id=account.id, starter_pack_id=self.starter_pack.id).exists()
        )

    def test_toggle_after_limit(self):
        account = baker.make("accounts.Account", discoverable=True)
        self.client.force_login(self.user)
        # baker.make("starter_packs.StarterPackAccount", starter_pack=self.starter_pack, account=account)
        baker.make("starter_packs.StarterPackAccount", starter_pack=self.starter_pack, _quantity=150)

        self.assertEqual(self.starter_pack.starterpackaccount_set.count(), 150)
        response = self.client.post(
            reverse(
                "toggle_account_to_starter_pack",
                kwargs={"starter_pack_slug": self.starter_pack.slug, "account_id": account.id},
            )
        )
        self.assertEqual(response.status_code, 200)

        # Make sure we can delete even after the limit:
        baker.make("starter_packs.StarterPackAccount", starter_pack=self.starter_pack, account=account)
        self.assertEqual(self.starter_pack.starterpackaccount_set.count(), 151)
        response = self.client.post(
            reverse(
                "toggle_account_to_starter_pack",
                kwargs={"starter_pack_slug": self.starter_pack.slug, "account_id": account.id},
            )
        )
        self.assertEqual(self.starter_pack.starterpackaccount_set.count(), 150)


class TestOwnerManagement(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.owner)
        cls.pack = baker.make("starter_packs.StarterPack", created_by=cls.owner)
        cls.pack.owners.add(cls.owner)
        # A second user who has logged into fedidevs (findable via search).
        cls.friend = baker.make("auth.User")
        baker.make(
            "mastodon_auth.AccountAccess",
            user=cls.friend,
            account__username_at_instance="@friend@instance.org",
            account__display_name="Friendly Person",
        )

    # --- permission semantics: owners, not created_by ---

    def test_added_owner_who_is_not_creator_can_edit(self):
        self.pack.owners.add(self.friend)
        self.client.force_login(self.friend)
        response = self.client.get(reverse("edit_starter_pack", args=[self.pack.slug]))
        self.assertEqual(response.status_code, 200)

    def test_creator_removed_from_owners_loses_access(self):
        self.pack.owners.add(self.friend)
        self.pack.owners.remove(self.owner)  # creator is no longer an owner
        self.client.force_login(self.owner)
        response = self.client.get(reverse("edit_starter_pack", args=[self.pack.slug]))
        self.assertEqual(response.status_code, 404)

    # --- manage owners page + search ---

    def test_manage_owners_page(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manage_owners", args=[self.pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage owners")
        self.assertContains(response, self.owner.accountaccess.account.username_at_instance)

    def test_non_owner_cannot_open_manage_page(self):
        self.client.force_login(self.friend)  # not an owner
        response = self.client.get(reverse("manage_owners", args=[self.pack.slug]))
        self.assertEqual(response.status_code, 404)

    def test_search_finds_logged_in_user(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manage_owners", args=[self.pack.slug]), {"q": "friend"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "@friend@instance.org")
        # The result carries an Invite button targeting this user.
        self.assertContains(response, reverse("invite_owner", args=[self.pack.slug, self.friend.id]))

    def test_search_excludes_existing_owners(self):
        self.pack.owners.add(self.friend)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manage_owners", args=[self.pack.slug]), {"q": "friend"})
        # Already an owner -> no "invite" action offered for them in search results.
        self.assertNotContains(response, reverse("invite_owner", args=[self.pack.slug, self.friend.id]))

    def test_search_excludes_invited_users(self):
        StarterPackInvitation.objects.create(starter_pack=self.pack, invited_user=self.friend, invited_by=self.owner)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manage_owners", args=[self.pack.slug]), {"q": "friend"})
        # Already invited -> no "invite" action offered for them in search results.
        self.assertNotContains(response, reverse("invite_owner", args=[self.pack.slug, self.friend.id]))

    # --- invite_owner ---

    def test_invite_creates_pending_invitation_not_owner(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("invite_owner", args=[self.pack.slug, self.friend.id]))
        self.assertEqual(response.status_code, 200)
        # Invited, but not yet an owner — they must accept first.
        self.assertFalse(self.pack.owners.filter(pk=self.friend.pk).exists())
        self.assertTrue(self.pack.invitations.filter(invited_user=self.friend, invited_by=self.owner).exists())

    def test_invite_without_account_access_is_rejected(self):
        ghost = baker.make("auth.User")  # never logged into fedidevs
        self.client.force_login(self.owner)
        response = self.client.post(reverse("invite_owner", args=[self.pack.slug, ghost.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.pack.invitations.filter(invited_user=ghost).exists())
        self.assertContains(response, "logged into Fedidevs yet")

    def test_invite_existing_owner_is_noop(self):
        self.pack.owners.add(self.friend)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("invite_owner", args=[self.pack.slug, self.friend.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.pack.invitations.filter(invited_user=self.friend).exists())

    def test_invite_twice_does_not_duplicate(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("invite_owner", args=[self.pack.slug, self.friend.id]))
        self.client.post(reverse("invite_owner", args=[self.pack.slug, self.friend.id]))
        self.assertEqual(self.pack.invitations.filter(invited_user=self.friend).count(), 1)

    def test_invite_blocked_at_max(self):
        # Fill up to the cap with a mix of owners and pending invitations.
        for _ in range(MAX_OWNERS - 1):
            filler = baker.make("auth.User")
            baker.make("mastodon_auth.AccountAccess", user=filler)
            self.pack.owners.add(filler)
        self.assertEqual(self.pack.owners.count(), MAX_OWNERS)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("invite_owner", args=[self.pack.slug, self.friend.id]))
        self.assertContains(response, "maximum number of owners")
        self.assertFalse(self.pack.invitations.filter(invited_user=self.friend).exists())

    def test_invite_blocked_when_owners_plus_invitations_at_max(self):
        # One owner + (MAX_OWNERS - 1) pending invitations == cap.
        for _ in range(MAX_OWNERS - 1):
            invitee = baker.make("auth.User")
            baker.make("mastodon_auth.AccountAccess", user=invitee)
            StarterPackInvitation.objects.create(starter_pack=self.pack, invited_user=invitee, invited_by=self.owner)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("invite_owner", args=[self.pack.slug, self.friend.id]))
        self.assertContains(response, "maximum number of owners")
        self.assertFalse(self.pack.invitations.filter(invited_user=self.friend).exists())

    def test_non_owner_cannot_invite(self):
        self.client.force_login(self.friend)  # not an owner
        response = self.client.post(reverse("invite_owner", args=[self.pack.slug, self.friend.id]))
        self.assertEqual(response.status_code, 404)

    # --- cancel_invitation ---

    def test_owner_cancels_invitation(self):
        StarterPackInvitation.objects.create(starter_pack=self.pack, invited_user=self.friend, invited_by=self.owner)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("cancel_invitation", args=[self.pack.slug, self.friend.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.pack.invitations.filter(invited_user=self.friend).exists())

    def test_non_owner_cannot_cancel_invitation(self):
        StarterPackInvitation.objects.create(starter_pack=self.pack, invited_user=self.friend, invited_by=self.owner)
        self.client.force_login(self.friend)  # not an owner
        response = self.client.post(reverse("cancel_invitation", args=[self.pack.slug, self.friend.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(self.pack.invitations.filter(invited_user=self.friend).exists())

    # --- accept / decline invitation ---

    def test_accept_invitation_makes_owner(self):
        StarterPackInvitation.objects.create(starter_pack=self.pack, invited_user=self.friend, invited_by=self.owner)
        self.client.force_login(self.friend)
        response = self.client.post(reverse("accept_invitation", args=[self.pack.slug]))
        self.assertRedirects(
            response, reverse("share_starter_pack", args=[self.pack.slug]), fetch_redirect_response=False
        )
        self.assertTrue(self.pack.owners.filter(pk=self.friend.pk).exists())
        self.assertFalse(self.pack.invitations.filter(invited_user=self.friend).exists())

    def test_only_invited_user_can_accept(self):
        StarterPackInvitation.objects.create(starter_pack=self.pack, invited_user=self.friend, invited_by=self.owner)
        stranger = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=stranger)
        self.client.force_login(stranger)  # has no invitation for this pack
        response = self.client.post(reverse("accept_invitation", args=[self.pack.slug]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.pack.owners.filter(pk=stranger.pk).exists())
        # The real invitee's invitation is untouched.
        self.assertTrue(self.pack.invitations.filter(invited_user=self.friend).exists())

    def test_accept_blocked_when_pack_at_max(self):
        StarterPackInvitation.objects.create(starter_pack=self.pack, invited_user=self.friend, invited_by=self.owner)
        # Pack reaches the owner cap after the invite was sent.
        for _ in range(MAX_OWNERS - 1):
            filler = baker.make("auth.User")
            baker.make("mastodon_auth.AccountAccess", user=filler)
            self.pack.owners.add(filler)
        self.assertEqual(self.pack.owners.count(), MAX_OWNERS)
        self.client.force_login(self.friend)
        self.client.post(reverse("accept_invitation", args=[self.pack.slug]))
        self.assertFalse(self.pack.owners.filter(pk=self.friend.pk).exists())
        # Invitation is kept so they can accept once a slot frees up.
        self.assertTrue(self.pack.invitations.filter(invited_user=self.friend).exists())

    def test_decline_invitation_removes_it(self):
        StarterPackInvitation.objects.create(starter_pack=self.pack, invited_user=self.friend, invited_by=self.owner)
        self.client.force_login(self.friend)
        response = self.client.post(reverse("decline_invitation", args=[self.pack.slug]))
        self.assertRedirects(response, reverse("starter_packs"), fetch_redirect_response=False)
        self.assertFalse(self.pack.invitations.filter(invited_user=self.friend).exists())
        self.assertFalse(self.pack.owners.filter(pk=self.friend.pk).exists())

    def test_pending_invitation_shown_on_starter_packs_page(self):
        StarterPackInvitation.objects.create(starter_pack=self.pack, invited_user=self.friend, invited_by=self.owner)
        self.client.force_login(self.friend)
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending invitations")
        self.assertContains(response, reverse("accept_invitation", args=[self.pack.slug]))
        self.assertContains(response, reverse("decline_invitation", args=[self.pack.slug]))

    # --- remove_owner ---

    def test_remove_owner(self):
        self.pack.owners.add(self.friend)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("remove_owner", args=[self.pack.slug, self.friend.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.pack.owners.filter(pk=self.friend.pk).exists())

    def test_cannot_remove_last_owner(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.pack.owners.count(), 1)
        response = self.client.post(reverse("remove_owner", args=[self.pack.slug, self.owner.id]))
        self.assertContains(response, "at least one owner")
        self.assertEqual(self.pack.owners.count(), 1)

    def test_owner_handles_shown_on_list_card(self):
        self.pack.published_at = timezone.now()  # show in the community tab
        self.pack.save()
        response = self.client.get(reverse("starter_packs"))
        self.assertEqual(response.status_code, 200)
        # The owner avatar (icon) and its popover handle both render.
        self.assertContains(response, self.owner.accountaccess.account.avatar_static)
        self.assertContains(response, self.owner.accountaccess.account.username_at_instance)
        # Template comments must not leak as literal text.
        self.assertNotContains(response, "bridges the gap")
        # Card carries the gradient header.
        self.assertContains(response, "linear-gradient(110deg, #8c52ff")

    def test_removing_self_redirects_home(self):
        self.pack.owners.add(self.friend)  # not the last owner, so removal is allowed
        self.client.force_login(self.owner)
        response = self.client.post(reverse("remove_owner", args=[self.pack.slug, self.owner.id]))
        self.assertEqual(response["HX-Redirect"], "/")
        self.assertFalse(self.pack.owners.filter(pk=self.owner.pk).exists())


@ddt
class TestShareStarterPack(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make("auth.User")
        baker.make(
            "mastodon_auth.AccountAccess",
            user=cls.user,
            account__activitypub_id="https://instance.org/users/createdbyuser",
        )
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.user, num_accounts=5, languages=[])
        cls.starter_pack.owners.add(cls.user)
        instance = baker.make("accounts.Instance")
        baker.make(
            "starter_packs.StarterPackAccount",
            starter_pack=cls.starter_pack,
            account__discoverable=True,
            account__instance_model=instance,
            account__activitypub_id="https://instance.org/users/user",
            _quantity=5,
        )

    def test_not_existing_starter_pack(self):
        response = self.client.get(reverse("share_starter_pack", args=["not-existing"]))
        self.assertEqual(response.status_code, 404)

    def test_share_starter_pack(self):
        response = self.client.get(reverse("share_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.starter_pack.title)
        self.assertContains(response, self.starter_pack.description)

        for account in self.starter_pack.starterpackaccount_set.all():
            with self.subTest("Check account"):
                self.assertContains(response, account.account.username)

        self.assertNotContains(response, "Edit")
        self.assertNotContains(response, "Delete")
        self.assertContains(response, "Follow all 5 accounts")

    def test_languages_shown_when_set(self):
        self.starter_pack.languages = ["fr", "de"]
        self.starter_pack.save(update_fields=["languages"])
        response = self.client.get(reverse("share_starter_pack", args=[self.starter_pack.slug]))
        self.assertContains(response, "🇫🇷 French")
        self.assertContains(response, "🇩🇪 German")

    def test_languages_hidden_when_unset(self):
        # The site's locale switcher renders bare flags (e.g. "🇫🇷 Français"), so we
        # assert the pack badge form ("🇫🇷 French", English name) is absent instead.
        self.assertEqual(self.starter_pack.languages, [])
        response = self.client.get(reverse("share_starter_pack", args=[self.starter_pack.slug]))
        self.assertNotContains(response, "🇫🇷 French")

    def test_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("share_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.starter_pack.title)
        self.assertContains(response, self.starter_pack.description)

        for account in self.starter_pack.starterpackaccount_set.all():
            with self.subTest("Check account"):
                self.assertContains(response, account.account.username)

        self.assertContains(response, "Edit")
        self.assertContains(response, "Delete")
        self.assertContains(response, "Follow all 5 accounts")

    def test_header_shows_gradient_and_account_avatars(self):
        response = self.client.get(reverse("share_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "linear-gradient(110deg, #8c52ff")
        # The pack's account avatars decorate the gradient header.
        account = self.starter_pack.starterpackaccount_set.first().account
        self.assertContains(response, account.avatar_static)
        # Template comments must not leak as literal text.
        self.assertNotContains(response, "spill left")

    def test_non_discoverable_accounts(self):
        Account.objects.update(discoverable=False)
        self.starter_pack.num_accounts = 0
        self.starter_pack.save()
        response = self.client.get(reverse("share_starter_pack", args=[self.starter_pack.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.starter_pack.title)
        self.assertContains(response, self.starter_pack.description)

        for account in self.starter_pack.starterpackaccount_set.all():
            with self.subTest("Check account"):
                self.assertNotContains(response, account.account.username)

        self.assertNotContains(response, "Edit")
        self.assertNotContains(response, "Delete")
        self.assertNotContains(response, "Follow all 5 accounts")

    def _set_up_orderable_accounts(self):
        """Give each account distinct, mutually contradicting sort keys.

        By id order: followers ascending, display name descending, account age
        descending (older accounts first), last activity ascending, and pack
        membership added in id order — so every sort option produces a
        different ordering.
        """
        now = timezone.now()
        accounts = list(Account.objects.filter(starterpackaccount__starter_pack=self.starter_pack).order_by("id"))
        for i, account in enumerate(accounts):
            account.followers_count = i
            account.display_name = f"Name {len(accounts) - i}"
            account.created_at = now - datetime.timedelta(days=i)
            account.last_status_at = now - datetime.timedelta(days=len(accounts) - i)
        Account.objects.bulk_update(accounts, ["followers_count", "display_name", "created_at", "last_status_at"])
        # created_at is auto_now_add, so it has to be set with update().
        for i, spa in enumerate(StarterPackAccount.objects.order_by("id")):
            StarterPackAccount.objects.filter(pk=spa.pk).update(created_at=now - datetime.timedelta(hours=i))
        return accounts

    @data(
        ("followers", [4, 3, 2, 1, 0]),
        ("recently_added", [0, 1, 2, 3, 4]),
        ("last_active", [4, 3, 2, 1, 0]),
        ("newest_account", [0, 1, 2, 3, 4]),
        ("alphabetical", [4, 3, 2, 1, 0]),
        ("not-a-valid-option", [4, 3, 2, 1, 0]),  # falls back to followers
    )
    @unpack
    def test_order_by(self, order_by, expected_indexes):
        accounts = self._set_up_orderable_accounts()
        response = self.client.get(reverse("share_starter_pack", args=[self.starter_pack.slug]), {"order_by": order_by})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [account.pk for account in response.context["accounts"]],
            [accounts[i].pk for i in expected_indexes],
        )

    def test_order_by_recently_added_ignores_other_packs(self):
        # Membership in another pack must not duplicate accounts or leak that
        # pack's added-at dates into the ordering.
        accounts = self._set_up_orderable_accounts()
        other_pack = baker.make("starter_packs.StarterPack")
        baker.make("starter_packs.StarterPackAccount", starter_pack=other_pack, account=accounts[0])
        response = self.client.get(
            reverse("share_starter_pack", args=[self.starter_pack.slug]), {"order_by": "recently_added"}
        )
        self.assertEqual(
            [account.pk for account in response.context["accounts"]],
            [account.pk for account in accounts],
        )

    def test_order_by_htmx_swaps_account_list(self):
        # Changing the select fires an htmx request that swaps just the list.
        accounts = self._set_up_orderable_accounts()
        response = self.client.get(
            reverse("share_starter_pack", args=[self.starter_pack.slug]),
            {"order_by": "recently_added"},
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "starter_pack_accounts.html")
        self.assertTemplateNotUsed(response, "share_starter_pack.html")
        self.assertEqual(
            [account.pk for account in response.context["accounts"]],
            [account.pk for account in accounts],
        )

    def test_sort_select_avoids_inline_js(self):
        # The CSP nonce policy blocks inline handlers, so the select must be
        # wired up with htmx targeting the account list wrapper.
        response = self.client.get(reverse("share_starter_pack", args=[self.starter_pack.slug]))
        self.assertContains(response, 'hx-target="#starter-pack-accounts"')
        self.assertContains(response, 'id="starter-pack-accounts"')
        self.assertNotContains(response, "onchange")

    @data(
        # ActivityPub:
        ('application/ld+json; profile="https://www.w3.org/ns/activitystreams"', "application/activity+json"),  # MUST
        ("application/activity+json", "application/activity+json"),  # SHOULD
        ("application/activity+json;q=0.5,text/html;q=0.4", "application/activity+json"),
        # JSON:
        ("application/json", "application/json"),
        ("application/json;q=0.5,text/html;q=0.4", "application/json"),
        # HTML:
        ("text/html", "text/html"),
        ("text/plain", "text/html"),
    )
    @unpack
    def test_api_formats(self, accept_header, expected_content_type):
        # Testing the content negotiation. See: https://www.w3.org/TR/activitypub/#retrieving-objects
        response = self.client.get(
            reverse("share_starter_pack", args=[self.starter_pack.slug]),
            headers={"accept": accept_header},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"].split(";")[0], expected_content_type)

    def test_api_plain_json(self):
        # Testing the plain JSON response
        url = reverse("share_starter_pack", args=[self.starter_pack.slug])
        response = self.client.get(
            url,
            headers={"accept": "application/json"},
        )

        payload = response.json()
        accounts = (
            Account.objects.filter(
                starterpackaccount__starter_pack=self.starter_pack,
                instance_model__isnull=False,
                instance_model__deleted_at__isnull=True,
                discoverable=True,
            )
            .select_related("accountlookup", "instance_model")
            .order_by("-followers_count")
        )
        self.assertEqual(
            payload,
            {
                "url": f"http://testserver{url}",
                "title": self.starter_pack.title,
                "description": self.starter_pack.description,
                "created_by": self.starter_pack.created_by.username,
                "created_at": self.starter_pack.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "updated_at": self.starter_pack.updated_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "published_at": self.starter_pack.published_at,
                "daily_follows": self.starter_pack.daily_follows,
                "weekly_follows": self.starter_pack.weekly_follows,
                "monthly_follows": self.starter_pack.monthly_follows,
                "accounts": [
                    {
                        "name": account.name,
                        "handle": account.username_at_instance,
                        "url": account.url,
                        "activitypub_id": account.activitypub_id,
                        "created_at": account.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                        "followers_count": account.followers_count,
                        "following_count": account.following_count,
                        "statuses_count": account.statuses_count,
                        "bot": account.bot,
                        "discoverable": account.discoverable,
                        "locked": account.locked,
                        "noindex": account.noindex,
                        "avatar": account.avatar,
                        "header": account.avatar,
                    }
                    for account in accounts
                ],
            },
        )

    def test_api_activitypub(self):
        # Testing the ActivityPub response
        url = reverse("share_starter_pack", args=[self.starter_pack.slug])
        response = self.client.get(
            url,
            headers={"accept": 'application/ld+json; profile="https://www.w3.org/ns/activitystreams"'},
        )

        # ActivityPub is kind of difficult to test for syntactically, but these will always be in there:
        self.assertContains(response, '"@context"')
        self.assertContains(response, '"https://www.w3.org/ns/activitystreams"')
        payload = response.json()

        accounts = (
            Account.objects.filter(
                starterpackaccount__starter_pack=self.starter_pack,
                instance_model__isnull=False,
                instance_model__deleted_at__isnull=True,
                discoverable=True,
            )
            .select_related("accountlookup", "instance_model")
            .order_by("-followers_count")
        )

        expected_payload = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Collection",
            "id": f"http://testserver{url}",
            "name": self.starter_pack.title,
            "summary": self.starter_pack.description,
            "attributedTo": self.starter_pack.created_by.accountaccess.account.activitypub_id,
            "published": self.starter_pack.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "updated": self.starter_pack.updated_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "image": {
                "type": "Image",
                "mediaType": "image/png",
                "url": payload["image"]["url"],
                "summary": "",
            },
            "generator": {
                "type": "Application",
                "name": "Fedidevs",
                "url": "http://testserver/",
            },
            "totalItems": accounts.count(),
            "items": [account.activitypub_id for account in accounts],
        }

        self.assertEqual(payload, expected_payload)


class TestPinAccountInStarterPack(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=cls.owner)
        cls.starter_pack = baker.make("starter_packs.StarterPack", created_by=cls.owner)
        cls.starter_pack.owners.add(cls.owner)
        cls.instance = baker.make("accounts.Instance", instance="instance.org")
        cls.popular = cls._make_account("popular", followers_count=100)
        cls.niche = cls._make_account("niche", followers_count=1)

    @classmethod
    def _make_account(cls, username, followers_count):
        account = baker.make(
            "accounts.Account",
            username=username,
            display_name=username.title(),
            username_at_instance=f"{username}@instance.org",
            note="python",
            url=f"https://instance.org/@{username}",
            discoverable=True,
            followers_count=followers_count,
            instance_model=cls.instance,
            emojis=[],
            roles=[],
            fields=[],
        )
        baker.make(
            "starter_packs.StarterPackAccount",
            starter_pack=cls.starter_pack,
            account=account,
            created_by=cls.owner,
        )
        return account

    def pin_url(self, account):
        return reverse("toggle_pin_in_starter_pack", args=[self.starter_pack.slug, account.pk])

    def share_url(self):
        return reverse("share_starter_pack", args=[self.starter_pack.slug])

    def test_pin_button_shown_on_review_page(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("review_starter_pack", args=[self.starter_pack.slug]))
        self.assertContains(response, f'hx-post="{self.pin_url(self.niche)}"')

    def test_pin_button_shown_on_add_accounts_page(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("edit_accounts_starter_pack", args=[self.starter_pack.slug]))
        self.assertContains(response, f'hx-post="{self.pin_url(self.niche)}"')

    def test_no_pin_button_on_share_page(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.share_url())
        self.assertNotContains(response, f'hx-post="{self.pin_url(self.niche)}"')

    def test_toggle_pin_and_unpin(self):
        self.client.force_login(self.owner)

        response = self.client.post(self.pin_url(self.niche))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(StarterPackAccount.objects.get(starter_pack=self.starter_pack, account=self.niche).pinned)
        self.assertContains(response, "Unpin this account")

        response = self.client.post(self.pin_url(self.niche))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StarterPackAccount.objects.get(starter_pack=self.starter_pack, account=self.niche).pinned)
        self.assertContains(response, "Pin this account to the top")

    def test_toggle_pin_requires_ownership(self):
        other_user = baker.make("auth.User")
        self.client.force_login(other_user)
        response = self.client.post(self.pin_url(self.niche))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(StarterPackAccount.objects.get(starter_pack=self.starter_pack, account=self.niche).pinned)

    def test_pin_limit(self):
        self.client.force_login(self.owner)
        for i in range(MAX_PINNED_ACCOUNTS):
            self._make_account(f"filler{i}", followers_count=5)
        StarterPackAccount.objects.filter(starter_pack=self.starter_pack).exclude(
            account__in=[self.popular, self.niche]
        ).update(pinned=True)

        response = self.client.post(self.pin_url(self.niche))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StarterPackAccount.objects.get(starter_pack=self.starter_pack, account=self.niche).pinned)
        self.assertContains(response, "You can pin at most")

    def test_pinned_account_listed_first_for_everyone(self):
        StarterPackAccount.objects.filter(starter_pack=self.starter_pack, account=self.niche).update(pinned=True)

        response = self.client.get(self.share_url())
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(
            content.index(f"pack-account-card-{self.niche.pk}"),
            content.index(f"pack-account-card-{self.popular.pk}"),
        )
        self.assertContains(response, "ring-amber-400")
        self.assertContains(response, "Pinned")

    def test_unpinned_pack_orders_by_followers(self):
        response = self.client.get(self.share_url())
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(
            content.index(f"pack-account-card-{self.popular.pk}"),
            content.index(f"pack-account-card-{self.niche.pk}"),
        )
        self.assertNotContains(response, "ring-amber-400")

    def test_removing_account_swaps_pin_button_to_disabled(self):
        self.client.force_login(self.owner)
        StarterPackAccount.objects.filter(starter_pack=self.starter_pack, account=self.niche).update(pinned=True)

        response = self.client.post(
            reverse("toggle_account_to_starter_pack", args=[self.starter_pack.slug, self.niche.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(f'id="pin-button-{self.niche.pk}"', content)
        self.assertIn("hx-swap-oob", content)
        self.assertIn("disabled", content)
        self.assertNotIn(f'hx-post="{self.pin_url(self.niche)}"', content)
        self.assertFalse(StarterPackAccount.objects.filter(starter_pack=self.starter_pack, account=self.niche).exists())

    def test_readding_account_swaps_pin_button_to_enabled_unpinned(self):
        self.client.force_login(self.owner)
        StarterPackAccount.objects.filter(starter_pack=self.starter_pack, account=self.niche).update(pinned=True)
        toggle_url = reverse("toggle_account_to_starter_pack", args=[self.starter_pack.slug, self.niche.pk])

        self.client.post(toggle_url)  # remove: drops the pin along with the membership row
        response = self.client.post(toggle_url)  # re-add
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("hx-swap-oob", content)
        self.assertIn(f'hx-post="{self.pin_url(self.niche)}"', content)
        self.assertFalse(StarterPackAccount.objects.get(starter_pack=self.starter_pack, account=self.niche).pinned)

    def test_stale_pin_toggle_returns_disabled_button(self):
        self.client.force_login(self.owner)
        StarterPackAccount.objects.filter(starter_pack=self.starter_pack, account=self.niche).delete()

        response = self.client.post(self.pin_url(self.niche))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(f'id="pin-button-{self.niche.pk}"', content)
        self.assertIn("disabled", content)
        self.assertNotIn(f'hx-post="{self.pin_url(self.niche)}"', content)

    def test_pinned_account_first_for_every_sort_option(self):
        # Alphabetically "Niche" < "Popular", so pinning popular must override the sort.
        StarterPackAccount.objects.filter(starter_pack=self.starter_pack, account=self.popular).update(pinned=True)

        response = self.client.get(self.share_url() + "?order_by=alphabetical")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(
            content.index(f"pack-account-card-{self.popular.pk}"),
            content.index(f"pack-account-card-{self.niche.pk}"),
        )


class TestParseHandle(TestCase):
    def test_valid_handles(self):
        for raw, expected in [
            ("pfefferle@notiz.blog", ("pfefferle", "notiz.blog")),
            ("@pfefferle@notiz.blog", ("pfefferle", "notiz.blog")),
            ("  @user@example.social  ", ("user", "example.social")),
            ("user@sub.example.co.uk", ("user", "sub.example.co.uk")),
            ("user@ünicode.example", ("user", "xn--nicode-2ya.example")),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(parse_handle(raw), expected)

    def test_invalid_handles(self):
        for raw in ["", "plainstring", "@user", "user@", "@user@nodot", "us er@example.com", "user@@example.com"]:
            with self.subTest(raw=raw):
                self.assertIsNone(parse_handle(raw))


class TestGetSubscribeUrl(TestCase):
    target = "http://testserver/s/abc/"

    def _webfinger_response(self, payload, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = payload
        return response

    @patch("starter_packs.remote_follow.httpx.get")
    def test_returns_filled_template(self, mock_get):
        mock_get.return_value = self._webfinger_response(
            {
                "links": [
                    {"rel": "self", "type": "application/activity+json", "href": "https://notiz.blog/author/matthias"},
                    {
                        "rel": "http://ostatus.org/schema/1.0/subscribe",
                        "template": "https://notiz.blog/wp-json/activitypub/1.0/interactions?uri={uri}",
                    },
                ]
            }
        )
        self.assertEqual(
            get_subscribe_url("pfefferle", "notiz.blog", self.target),
            "https://notiz.blog/wp-json/activitypub/1.0/interactions?uri=http%3A%2F%2Ftestserver%2Fs%2Fabc%2F",
        )
        self.assertEqual(mock_get.call_args.args, ("https://notiz.blog/.well-known/webfinger",))
        self.assertEqual(mock_get.call_args.kwargs["params"], {"resource": "acct:pfefferle@notiz.blog"})

    @patch("starter_packs.remote_follow.httpx.get")
    def test_no_subscribe_link(self, mock_get):
        mock_get.return_value = self._webfinger_response({"links": [{"rel": "self", "href": "https://a.b/c"}]})
        self.assertIsNone(get_subscribe_url("user", "example.com", self.target))

    @patch("starter_packs.remote_follow.httpx.get")
    def test_rejects_non_https_template(self, mock_get):
        mock_get.return_value = self._webfinger_response(
            {"links": [{"rel": "http://ostatus.org/schema/1.0/subscribe", "template": "javascript:alert(1)?{uri}"}]}
        )
        self.assertIsNone(get_subscribe_url("user", "example.com", self.target))

    @patch("starter_packs.remote_follow.httpx.get")
    def test_rejects_template_without_uri_placeholder(self, mock_get):
        mock_get.return_value = self._webfinger_response(
            {"links": [{"rel": "http://ostatus.org/schema/1.0/subscribe", "template": "https://a.b/follow"}]}
        )
        self.assertIsNone(get_subscribe_url("user", "example.com", self.target))

    @patch("starter_packs.remote_follow.httpx.get")
    def test_webfinger_404(self, mock_get):
        mock_get.return_value = self._webfinger_response({}, status_code=404)
        self.assertIsNone(get_subscribe_url("user", "example.com", self.target))

    @patch("starter_packs.remote_follow.httpx.get", side_effect=httpx.ConnectError("boom"))
    def test_webfinger_network_error(self, mock_get):
        self.assertIsNone(get_subscribe_url("user", "example.com", self.target))

    @patch("starter_packs.remote_follow.httpx.get")
    def test_webfinger_invalid_json(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.json.side_effect = ValueError("not json")
        mock_get.return_value = response
        self.assertIsNone(get_subscribe_url("user", "example.com", self.target))


class TestRemoteFollowStarterPack(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.starter_pack = baker.make("starter_packs.StarterPack", published_at=timezone.now())
        cls.url = reverse("remote_follow_starter_pack", kwargs={"starter_pack_slug": cls.starter_pack.slug})
        cls.pack_url = reverse("share_starter_pack", kwargs={"starter_pack_slug": cls.starter_pack.slug})

    def test_share_page_shows_remote_follow_form_when_logged_out(self):
        response = self.client.get(self.pack_url)
        self.assertContains(response, self.url)
        self.assertContains(response, "Follow with your fediverse handle")

    def test_share_page_hides_remote_follow_form_when_logged_in(self):
        user = baker.make("auth.User")
        baker.make("mastodon_auth.AccountAccess", user=user)
        self.client.force_login(user)
        response = self.client.get(self.pack_url)
        self.assertNotContains(response, "Follow with your fediverse handle")

    @patch("starter_packs.views.get_subscribe_url")
    def test_redirects_to_subscribe_url(self, mock_get_subscribe_url):
        mock_get_subscribe_url.return_value = (
            "https://notiz.blog/wp-json/activitypub/1.0/interactions?uri=http%3A%2F%2Ftestserver%2Fs%2Fabc%2F"
        )
        response = self.client.post(self.url, {"handle": "@pfefferle@notiz.blog"})
        self.assertRedirects(response, mock_get_subscribe_url.return_value, fetch_redirect_response=False)
        mock_get_subscribe_url.assert_called_once_with("pfefferle", "notiz.blog", f"http://testserver{self.pack_url}")

    @patch("starter_packs.views.get_subscribe_url", return_value=None)
    def test_error_when_no_subscribe_endpoint(self, mock_get_subscribe_url):
        response = self.client.post(self.url, {"handle": "user@example.com"}, follow=True)
        self.assertRedirects(response, self.pack_url)
        self.assertContains(response, "remote follow endpoint")

    def test_error_on_invalid_handle(self):
        response = self.client.post(self.url, {"handle": "not-a-handle"}, follow=True)
        self.assertRedirects(response, self.pack_url)
        self.assertContains(response, "Please enter a fediverse handle")

    def test_missing_handle(self):
        response = self.client.post(self.url, {}, follow=True)
        self.assertRedirects(response, self.pack_url)
        self.assertContains(response, "Please enter a fediverse handle")

    def test_deleted_pack_404(self):
        pack = baker.make("starter_packs.StarterPack", deleted_at=timezone.now())
        url = reverse("remote_follow_starter_pack", kwargs={"starter_pack_slug": pack.slug})
        response = self.client.post(url, {"handle": "user@example.com"})
        self.assertEqual(response.status_code, 404)

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
