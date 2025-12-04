#!/usr/bin/env python

import collections
import json
import threading
from typing import Any

import snappy

from sotoki.constants import NB_PAGINATED_USERS
from sotoki.utils.shared import logger, shared


class TopDict(collections.UserDict):
    """A fixed-sized dict that keeps only the highest values"""

    def __init__(self, maxlen: int):
        super().__init__()
        self.maxlen = maxlen
        self.lock = threading.Lock()

    def __setitem__(self, key, value):
        with self.lock:
            # we're full, might not accept value
            if len(self) >= self.maxlen:
                # value is bellow our min, don't care
                min_val = min(self.values())
                if value < min_val:
                    return

                # value should be in top, let's remove our min to allow it
                min_key = list(self.keys())[list(self.values()).index(min_val)]
                del self[min_key]
            super().__setitem__(key, value)

    def sorted(self):
        return [k for k, _ in sorted(self.items(), key=lambda x: x[1], reverse=True)]


class UsersDatabase:
    """Users related Database operations

    We mainly store some basic profile-details for each user so that we can display
    the user card wherever needed (in questions listing and inside question pages).
    Most important datapoint is the name (DisplayName) followed by Reputation (a score)
    We also store the number of badges owned by class (gold, silver, bronze) as this
    is this is an extension to thre reputation.

    We store this as a list in U:{userId} key for each user

    We also have a sorted set of UserIds scored by Reputation.
    Because we first go through Posts to eliminate all Users without interactions,
    we first gather an un-ordered list of UserIds: a non-sorted set.
    Once we're trhough with this step, we create the sorted one and trash the first one.

    List of users is essential to exclude users without interactions, so we don't
    create pages for them.

    Sorted list of users allows us to build a page with the list of Top users.

    Note: interactions associated with Deleted users are recorded to a name and not
    a UserId.

    Note: we don't track User's profile image URL as we store images in-Zim at a fixed
    location based on UserId."""

    def __init__(self):
        self._top_users = TopDict(NB_PAGINATED_USERS)

        # temp set to hold all active users' IDs
        self._all_users_ids = set()

        # total number of active users
        self.nb_users = 0

    @staticmethod
    def user_key(user_id):
        return f"U:{user_id}"

    def record_user(self, user: dict[str, Any]):
        """record basic user details to MEM at U:{id} key

        Name, Reputation, NbGoldBages, NbSilverBadges, NbBronzeBadges"""

        # record score in top mapping
        self._top_users[user["Id"]] = user["Reputation"]

        # record profile details into individual key
        shared.database.pipe.set(
            self.user_key(user["Id"]),
            snappy.compress(
                json.dumps(
                    (
                        user["DisplayName"],
                        user["Reputation"],
                        user["nb_gold"],
                        user["nb_silver"],
                        user["nb_bronze"],
                    )
                )
            ),
        )

        shared.database.bump_seen()
        shared.database.commit_maybe()

    def ack_users_ids(self):
        """dump or load users_ids"""
        all_users_ids_fpath = shared.build_dir / "all_users_ids.json"
        if not self._all_users_ids and all_users_ids_fpath.exists():
            logger.debug(f"loading all_users_ids from {all_users_ids_fpath.name}")
            with open(all_users_ids_fpath) as fh:
                self._all_users_ids = set(json.load(fh))
        else:
            with open(all_users_ids_fpath, "w") as fh:
                json.dump(list(self._all_users_ids), fh, indent=4)

    def cleanup_users(self):
        """frees list of active users that we won't need anymore. sets nb_users

        Loads top_users from JSON dump if avail and top_users are empty"""
        self.nb_users = len(self._all_users_ids)
        del self._all_users_ids
        self.top_users = self._top_users.sorted()
        del self._top_users

        top_users_fpath = shared.build_dir / "top_users.json"
        if not self.top_users and top_users_fpath.exists():
            logger.debug(f"loading top_users from {top_users_fpath.name}")
            with open(top_users_fpath) as fh:
                self.top_users = json.load(fh)
        else:
            with open(top_users_fpath, "w") as fh:
                json.dump(self.top_users, fh, indent=4)

    def get_user_full(self, user_id: int) -> dict[str, Any] | None:
        """All recorded information for a UserId

        id, name, rep, nb_gold, nb_silver, nb_bronze"""
        user = shared.database.safe_get(self.user_key(user_id))
        if not user:
            return None
        user = json.loads(snappy.decompress(user))
        return {
            "id": user_id,
            "name": user[0],
            "rep": user[1],
            "nb_gold": user[2],
            "nb_silver": user[3],
            "nb_bronze": user[4],
        }

    def is_active_user(self, user_id):
        """whether a user_id is considered active (has interaction in content)

        WARN: only valid during Users listing step"""
        return user_id in self._all_users_ids
