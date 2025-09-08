import logging

from anthropic import Anthropic
from anthropic.types import TextBlock
from django.conf import settings
from django_rich.management import RichCommand

from accounts.models import AccountLookup

logger = logging.getLogger(__name__)


def current_cost(input_tokens, output_tokens, input_token_price, output_token_price):
    return round(input_tokens * input_token_price + output_tokens * output_token_price, 6)


class Command(RichCommand):
    help = "Indexes accounts in the database"

    def handle(self, *args, **options):
        if not (api_key := settings.ANTHROPIC_API_KEY):
            logger.error("No Anthropic API key found, set the `ANTHROPIC_API_KEY` env variable/value in .env file")
            return
        client = Anthropic(
            api_key=api_key,
        )
        output_tokens = 0
        input_tokens = 0
        output_token_price = 1.25 / 1_000_000
        input_token_price = 0.25 / 1_000_000
        processed = 0
        total_accounts = AccountLookup.objects.filter(account_type="!").count()
        while True:
            accounts_lookup = AccountLookup.objects.filter(account_type="!").order_by("-followers_count")[:5]
            if not accounts_lookup:
                logger.info("All done!")
                break
            to_update = set()
            for account in accounts_lookup:
                prompt = f"{account.text.replace(',', ' ').replace('\n', ' ')}"
                message = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=10,
                    system="The input is Mastodon account text data including a bio, name, and link. You have to figure out if the account is a human or project/company/bot. Classify it as a human (H) if it has a name, surname, hobbies, refers to themselves in singular, uses I or has pronounes set. Classify as project (P) if the account is a project/company/bot and it refers to itself in plural (we) and doesn't have a name/surname. Output only the classification letter nothing else.",
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                )
                # Get the text content from the response
                if message.content and len(message.content) > 0:
                    content_block = message.content[0]
                    if isinstance(content_block, TextBlock):
                        res = content_block.text.strip()
                    else:
                        logger.error("Unexpected content type: %s", type(content_block))
                        continue
                else:
                    logger.error("No content in response")
                    continue

                if res not in ["H", "P"]:
                    logger.error("Invalid classification %s", res)
                    continue

                output_tokens += message.usage.output_tokens
                input_tokens += message.usage.input_tokens
                account.account_type = res
                to_update.add(account)
            AccountLookup.objects.bulk_update(to_update, ["account_type"])
            processed += len(to_update)
            cur_cst = current_cost(input_tokens, output_tokens, input_token_price, output_token_price)

            logger.info(
                "Processed %s accounts\ntotal_cost: %.6f\nExpected total cost: %.6f",
                processed,
                cur_cst,
                (cur_cst / processed) * total_accounts,
            )

        total_accounts_for_following = AccountLookup.objects.filter(follower_type="?").count()
        celebrities = 0
        best = 0
        peasants = 0
        for account_lookup in (to_update := AccountLookup.objects.filter(follower_type="?")):
            try:
                follower_ratio = account_lookup.followers_count / account_lookup.following_count
            except ZeroDivisionError:
                follower_ratio = 0

            if account_lookup.followers_count > 2000 and follower_ratio > 10:
                account_lookup.follower_type = "C"
                celebrities += 1
            elif (
                account_lookup.followers_count > 100
                and account_lookup.following_count > 100
                and 0.5 < follower_ratio < 4
            ):
                account_lookup.follower_type = "B"
                best += 1
            else:
                account_lookup.follower_type = "P"
                peasants += 1
        AccountLookup.objects.bulk_update(to_update, ["follower_type"], batch_size=100)
        logger.info(
            "Processed %s accounts\nCelebreties: %s\nBest: %s\nPeasants: %s\n",
            total_accounts_for_following,
            celebrities,
            best,
            peasants,
        )
