import json

from django.core.management.base import BaseCommand, CommandError

from api.youtube import YouTubeImportError, fetch_youtube_prices


class Command(BaseCommand):
    help = "Fetch recent videos from the configured YouTube channel and save parsed prices."

    def add_arguments(self, parser):
        parser.add_argument("--max-results", type=int, default=200, help="Maximum recent uploads to inspect (1-200).")

    def handle(self, *args, **options):
        try:
            result = fetch_youtube_prices(options["max_results"])
        except YouTubeImportError as exc:
            for entry in exc.logs:
                self.stdout.write(json.dumps(entry, ensure_ascii=False))
            raise CommandError(str(exc)) from exc
        for entry in result["logs"]:
            self.stdout.write(json.dumps(entry, ensure_ascii=False))
        self.stdout.write(self.style.SUCCESS(
            f"Status: {result['status']}; checked {result['videos_checked']} videos; "
            f"added {result['added']}, updated {result['updated']}, skipped {result['skipped']}."
        ))
