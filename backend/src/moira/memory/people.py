"""People (§7.8): resolve names against aliases; two Joshes stay two people."""

import sqlite3

from moira import ids
from moira.db.repos import people as repo
from moira.db.repos.people import Person
from moira.memory.validate import PersonRef


def _matches(p: Person, name: str) -> bool:
    low = name.strip().lower()
    names = [p.display_name, *p.aliases]
    return any(low == n.lower() or low.split()[0] == n.lower().split()[0] for n in names if n)


def resolve(conn: sqlite3.Connection, refs: list[PersonRef], *, now: int) -> list[int]:
    """Person ids for the validated references, creating people when needed."""
    out: list[int] = []
    people = repo.all_people(conn)
    for ref in refs:
        if ref.person_id is not None:
            out.append(ref.person_id)
            continue
        same = [p for p in people if _matches(p, ref.name)]
        hint = ref.hint.strip()
        if same:
            # A clearly different hint ("coworker" vs "friend from school") means another person.
            differs = hint and all(
                p.disambiguator and p.disambiguator.lower() != hint.lower() for p in same
            )
            if not differs:
                out.append(max(same, key=lambda p: p.created_at).id)
                continue
        person = repo.create(
            conn,
            public_id=ids.new("p_"),
            display_name=ref.name.strip(),
            now=now,
            aliases=[ref.name.strip().split()[0]],
            disambiguator=hint,
        )
        people.append(person)
        out.append(person.id)
    return list(dict.fromkeys(out))


def find_by_name(conn: sqlite3.Connection, name: str) -> Person | None:
    for p in repo.all_people(conn):
        if _matches(p, name):
            return p
    return None
