import logging

from django.conf import settings
from django_rich.management import RichCommand
from openai import OpenAI

from accounts.models import AccountLookup

logger = logging.getLogger(__name__)


def current_cost(prompt_tokens, completion_tokens, prompt_token_price, completion_token_price):
    return round(prompt_tokens * prompt_token_price + completion_tokens * completion_token_price, 6)


class Command(RichCommand):
    help = "Indexes accounts in the database"

    def handle(self, *args, **options):
        if not (api_key := settings.OPENAI_API_KEY):
            logger.error("No OpenAI API key found, set the `OPENAI_API_KEY` env variable/value in .env file")
            return
        client = OpenAI(
            api_key=api_key,
        )
        completion_tokens = 0
        prompt_tokens = 0
        completion_token_price = 0.600 / 1_000_000
        prompt_token_price = 0.150 / 1_000_000
        processed = 0
        total_accounts = AccountLookup.objects.filter(account_type="s").count()
        while True:
            accounts_lookup = AccountLookup.objects.filter(account_type="s").order_by("-followers_count")[:5]
            if not accounts_lookup:
                logger.info("All done!")
                break
            to_update = set()
            for account in accounts_lookup:
                prompt = f"{account.text.replace(',', ' ').replace('\n', ' ')}"
                completion = client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": "The input is Mastodon account text data including a bio, name, and link. You have to figure out if the account is a human or project/company/bot. Classify it as a human (H) if it has a name, surname, hobbies, refers to themselves in singular, uses I or has pronounes set. Classify as project (P) if the account is a project/company/bot and it refers to itself in plural (we) and doesn't have a name/surname. Output only the classification letter nothing else.",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    model="gpt-4o-mini",
                )
                res = completion.choices[0].message.content.strip()
                if res not in ["H", "P"]:
                    logger.error("Invalid classification %s", res)
                    continue

                completion_tokens += completion.usage.completion_tokens
                prompt_tokens += completion.usage.prompt_tokens
                account.account_type = res
                to_update.add(account)
            AccountLookup.objects.bulk_update(to_update, ["account_type"])
            processed += len(to_update)
            cur_cst = current_cost(prompt_tokens, completion_tokens, prompt_token_price, completion_token_price)

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
        AccountLookup.objects.bulk_update(to_update, ["follower_type"])
        logger.info(
            "Processed %s accounts\nCelebreties: %s\nBest: %s\nPeasants: %s\n",
            total_accounts_for_following,
            celebrities,
            best,
            peasants,
        )
