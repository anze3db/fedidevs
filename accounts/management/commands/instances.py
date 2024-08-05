import asyncio
import logging

import httpx
from asgiref.sync import async_to_sync
from django_rich.management import RichCommand

from accounts.models import Instance

INSTANCES = {
    "aus.social",
    "awscommunity.social",
    "bayes.club",
    "bitbang.social",
    "blahaj.social",
    "c.im",
    "c3d2.social",
    "chaos.social",
    "cloud-native.social",
    "cyberplace.social",
    "data-folks.masto.host",
    "defcon.social",
    "digitalcourage.social",
    "discuss.systems",
    "dmv.community",
    "dotnet.social",
    "drupal.community",
    "emacs.ch",
    "en.osm.town",
    "exquisite.social",
    "fedi.simonwillison.net",
    "fedi.turbofish.cc",
    "fedi.wersdoerfer.de",
    "floss.social",
    "fosstodon.org",
    "framapiaf.org",
    "freiburg.social",
    "freie-re.de",
    "front-end.social",
    "functional.cafe",
    "furry.engineer",
    "gamelinks007.net",
    "Gardenstate.social",
    "genomic.social",
    "graphics.social",
    "graz.social",
    "gyptazy.ch",
    "hachyderm.io",
    "hapyyr.com",
    "hometech.social",
    "hostsharing.coop",
    "indieweb.social",
    "infosec.exchange",
    "iosdev.space",
    "jvm.social",
    "k8s.social",
    "kolektiva.social",
    "layer8.space",
    "linh.social",
    "linuxrocks.online",
    "ma.fellr.net",
    "macaw.social",
    "mamot.fr",
    "mas.to",
    "mast.hpc.social",
    "masto.ai",
    "masto.machlis.com",
    "masto.pt",
    "mastodon-belgium.be",
    "mastodon.blaede.family",
    "mastodon.brown-silva.social",
    "mastodon.cloud",
    "mastodon.gamedev.place",
    "mastodon.green",
    "mastodon.ie",
    "mastodon.imichka.me",
    "mastodon.km6g.us",
    "mastodon.matrix.org",
    "mastodon.melroy.org",
    "mastodon.nl",
    "mastodon.online",
    "mastodon.org.uk",
    "mastodon.sdf.org",
    "mastodon.seattlematrix.org",
    "mastodon.social",
    "mastodon.terabyte-computing.com",
    "mastodon.theorangeone.net",
    "mastodon.uno",
    "mastodon.world",
    "mastodon.xyz",
    "mastodonapp.uk",
    "mathstodon.xyz",
    "mementomori.social",
    "metalhead.club",
    "mozilla.social",
    "mstdn.party",
    "mstdn.social",
    "mtd.pythonasia.org",
    "nkantar.social",
    "noc.social",
    "novaloop.social",
    "ohai.social",
    "oldbytes.space",
    "phparch.social",
    "phpc.social",
    "piaille.fr",
    "pouet.chapril.org",
    "procolix.social",
    "publicidentity.net",
    "rstats.me",
    "ruby.social",
    "ruhr.social",
    "scicomm.xyz",
    "seocommunity.social",
    "sfba.social",
    "sigmoid.social",
    "social.akrabat.com",
    "social.anoxinon.de",
    "social.codethink.co.uk",
    "social.coop",
    "social.diva.exchange",
    "social.ei8fdb.org",
    "social.headbright.eu",
    "social.jacklinke.com",
    "social.juanlu.space",
    "social.lfx.dev",
    "social.lutra-it.eu",
    "social.nitrokey.com",
    "social.opensource.org",
    "social.ridetrans.it",
    "social.rochacbruno.com",
    "social.screamingatmyscreen.com",
    "social.tchncs.de",
    "social.tinygo.org",
    "social.vmbrasseur.com",
    "strangeobject.space",
    "subdued.social",
    "symas.social",
    "tech.lgbt",
    "techhub.social",
    "technews.social",
    "techtoots.com",
    "tekton.network",
    "tilde.zone",
    "tooot.im",
    "toot.bike",
    "toot.cafe",
    "toot.io",
    "toot.teckids.org",
    "toot.works",
    "tooting.ch",
    "toots.dgplug.org",
    "toots.n7.gg",
    "ubuntu.social",
    "umbracocommunity.social",
    "universeodon.com",
    "vickerson.me",
    "vmst.io",
    "wetdry.world",
}

logger = logging.getLogger(__name__)


async def process_instances(instances):
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[fetch(client, instance) for instance in instances])
        for model_instance, instance in results:
            if not model_instance:
                continue
            await Instance.objects.aupdate_or_create(
                instance=instance,
                defaults={
                    k: v
                    for k, v in model_instance.items()
                    if k
                    in {
                        # Allowlist fields to store:
                        "domain",
                        "title",
                        "version",
                        "source_url",
                        "description",
                        "usage",
                        "thumbnail",
                        "languages",
                        "configuration",
                        "registrations",
                        "contact",
                        "rules",
                    }
                },
            )
            logger.info("%s ok", instance)


async def fetch(client, instance) -> tuple[dict | None, str]:
    try:
        response = await client.get(
            f"https://{instance}/api/v2/instance",
            timeout=5,
        )
    except httpx.HTTPError:
        logger.error("Http error when indexing %s", instance)
        return None, instance
    except Exception as e:
        logger.error("Unknown error when indexing %s, %s", instance, e)
        return None, instance
    if response.status_code != 200:
        logger.error("Error status code for %s", instance)
        return None, instance
    return response.json(), instance


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def add_arguments(self, parser):
        parser.add_argument("--instances", type=str, nargs="?", default=None)

    def handle(
        self,
        instances=None,
        *args,
        **options,
    ):
        if instances:
            to_index = instances.split(",")
        else:
            to_index = INSTANCES

        self.main(to_index)

    @async_to_sync
    async def main(self, to_index):
        await process_instances(to_index)
