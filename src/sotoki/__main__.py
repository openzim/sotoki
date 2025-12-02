import sys

from sotoki.context import Context
from sotoki.entrypoint import prepare_context
from sotoki.utils.exceptions import DatabaseError

logger = Context.logger


def main():

    scraper: StackExchangeToZim | None = None

    try:
        prepare_context(sys.argv[1:])

        # import this only once the Context has been initialized, so that it gets an
        # initialized context
        from sotoki.scraper import StackExchangeToZim  # noqa: PLC0415

        scraper = StackExchangeToZim()
        scraper.run()
    except SystemExit:
        logger.error("Scraper failed, exiting")
        raise
    except DatabaseError as exc:
        logger.critical("Unable to initialize database. Check --redis-url")
        raise SystemExit(2) from exc
    except Exception as exc:
        logger.exception(exc)
        logger.error(f"Scraper failed with the following error: {exc}")
        raise SystemExit(1) from exc
    finally:
        if scraper:
            scraper.cleanup()


if __name__ == "__main__":
    main()
