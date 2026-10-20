from django.core.management.base import BaseCommand, CommandError

from api.youtube import YouTubeImportError, fetch_youtube_prices


class Command(BaseCommand):
    help = "Fetch recent videos from the configured YouTube channel and save parsed prices."

    def add_arguments(self, parser):
        parser.add_argument("--max-results", type=int, default=50)

    def handle(self, *args, **options):
        try:
            result = fetch_youtube_prices(options["max_results"])
        except YouTubeImportError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Checked {result['videos_checked']} videos; added {result['added']}, "
            f"updated {result['updated']}, skipped {result['skipped']}."
        ))
