from django.core import management
from django_rich.management import RichCommand

from accounts.models import Account
from starter_packs.models import StarterPack, StarterPackAccount

"@CarineFouteau@mediapart.social,@AmeliePoinssot@piaille.fr,@AnttonRouget@piaille.fr,@JeromeHourdeaux@mamot.fr,@mathieu2jean@mediapart.social,@mauduit@mediapart.social,@bougon@mediapart.social,@gdelac@piaille.fr,@ManuRionde@piaille.fr,@gaetan@mediapart.social,@Vincent@mediapart.social,@tk@social.apreslanu.it,@OpenPony@piaille.fr,@kaaate@mediapart.social,@yan@potate.space,@liezah@piaille.fr,@tarikover@mastodon.social,@liviagarrigue@piaille.fr,@sabrinakassa@piaille.fr,@dan_mdpt@piaille.fr,@lenabred@mastodon.top,@marineturchi@piaille.fr,@RGodin@mastodon.social,@Morange@piaille.fr,@justinebrabant@piaille.fr,@youmnikezzouf@piaille.fr,@ellensalvi@piaille.fr,@faizazer@piaille.fr,@MathildeGoanec@mastodon.social,@donatien@mediapart.social,@armelbaudet@mediapart.social,@AlexandraB@piaille.fr,@gueugneau@mamot.fr,@justinevernier@eldritch.cafe,@SimonToupet@mamot.fr,@oliviap@mastodon.top,@renaudcreus@mediapart.social,@FabriceB@mediapart.social,@charline@mediapart.social,@cecilia@mediapart.social,@prisciana@mediapart.social,@claire@mediapart.social,@celeste@mediapart.social,@EdwyPlenel@mamot.fr,@jeremyb@mastodon.social,@elsaquintolet@mediapart.social,@Paulinelm@mediapart.social ,@CecH@piaille.fr,@gbprod@piaille.fr,@mediapart@mediapart.social,@mediapartblogs@mediapart.social,@Marsactu@mastodon.social,@Rue89Strasbourg@mas.to,@splann@mamot.fr,@_infoLibre@mastodon.world,@theintercept@journa.host,@correctiv_org@correctiv.social,@apache_be@mastodon.online"


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def add_arguments(self, parser):
        parser.add_argument("--starter-pack-slug", type=str, nargs="?", default=None)
        parser.add_argument("--accounts", type=str, nargs="?", default=None)

    def handle(
        self,
        *args,
        starter_pack_slug=None,
        accounts=None,
        **options,
    ):
        accounts = accounts.split(",")
        starter_pack = StarterPack.objects.get(slug=starter_pack_slug)
        for account in accounts:
            account_str = account.strip().lower()
            if not Account.objects.filter(username_at_instance=account_str).exists():
                management.call_command("crawlone", user=account_str[1:])

        account_models = Account.objects.filter(username_at_instance__in=accounts)
        starter_pack_accounts = [
            StarterPackAccount(starter_pack=starter_pack, account=account) for account in account_models
        ]
        StarterPackAccount.objects.bulk_create(starter_pack_accounts, ignore_conflicts=True)
