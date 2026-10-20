This folder contains integration tests, testing how the scraper behaves end-to-end
on a real, minimal Stack Exchange domain.

They are targeted at being run from the scraper Docker image from GitHub workflow(s),
readonly on the ZIM file produced by a real scrape.

They assert that the ZIM contains the important files, that they are not empty and
that the metadata is correct, since zimcheck alone would happily accept a ZIM with
only a very minimal `index.html` (which would be a full regression).
