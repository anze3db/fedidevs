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
        total_accounts = AccountLookup.objects.count()
        while True:
            accounts_lookup = AccountLookup.objects.filter(account_type="!").order_by("-followers_count")[:5]
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
                            "content": "You are a CSV classifier. The input is Mastodon account text data including a bio, name, and link. You have to figure out if the account is a human or project/company/bot. Classify it as a human (H) if it has a name, surname, hobbies, refers to themselves in singular, uses I or has pronounes set. Classify as project (P) if the account is a project/company/bot and it refers to itself in plural (we) and doesn't have a name/surname. Output only the classification letter nothing else.",
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
                "Processed %s accounts\ntotal_cost: %.6f\ncost per account: %.6f\nExpected total cost: %.6f",
                processed,
                cur_cst,
                cur_cst / processed,
                (cur_cst / processed) * total_accounts,
            )
