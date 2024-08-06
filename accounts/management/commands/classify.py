import logging
from collections import Counter

from django.conf import settings
from django_rich.management import RichCommand
from openai import OpenAI

from accounts.models import AccountLookup

logger = logging.getLogger(__name__)


def current_cost(prompt_tokens, completion_tokens, prompt_token_price, completion_token_price):
    logger.info("Prompt cost: %s", round(prompt_tokens * prompt_token_price, 6))
    logger.info("Completion cost: %s", round(completion_tokens * completion_token_price, 6))
    logger.info(
        "Total cost: %s", round(prompt_tokens * prompt_token_price + completion_tokens * completion_token_price, 6)
    )


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
        while True:
            accounts_lookup = AccountLookup.objects.filter(account_type="!")[:20]
            if not accounts_lookup:
                logger.info("All done!")
                current_cost(prompt_tokens, completion_tokens, prompt_token_price, completion_token_price)
                break
            pk_to_al = {al.pk: al for al in accounts_lookup}
            lines = ["id,text"]
            for account in accounts_lookup:
                prompt = f"{account.pk},{account.text.replace(',', ' ').replace('\n', ' ')}"
                lines.append(prompt)
            completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a CSV classifier. The input is a CSV file with two columns, id and text representing Mastodon accounts that are either humans or projects/companies/bots. For each account, you have to classify it as a human (H) if it has a name, surname, hobbies, refers to themselves in singular, uses I or has pronounes set. Classify as project (P) if the account is a project/company/bot and it refers to itself in plural (we) and doesn't have a name/surname. Output only the account id and the classification letter seperated by a comma.",
                    },
                    {
                        "role": "user",
                        "content": "\n".join(lines),
                    },
                ],
                model="gpt-4o-mini",
            )
            res = completion.choices[0].message.content
            completion_tokens += completion.usage.completion_tokens
            prompt_tokens += completion.usage.prompt_tokens
            to_update = set()
            cnt = Counter()
            for out in res.splitlines():
                if "," not in out:
                    continue
                account_id, account_type = out.split(",")
                cnt.update([account_type.strip()])
                pk_to_al[int(account_id)].account_type = account_type.strip()
                to_update.add(pk_to_al[int(account_id)])
            AccountLookup.objects.bulk_update(accounts_lookup, ["account_type"])
            logger.info(cnt)
            current_cost(prompt_tokens, completion_tokens, prompt_token_price, completion_token_price)
