"""Print waitlist sign-ups as CSV (Phase 0 validation).

python -m app.jobs.export_waitlist > waitlist.csv
"""

import csv
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import WaitlistSignup


def main() -> None:
    writer = csv.writer(sys.stdout)
    writer.writerow(["email", "source", "note", "created_at"])
    with SessionLocal() as db:
        for row in db.scalars(select(WaitlistSignup).order_by(WaitlistSignup.created_at)):
            writer.writerow(
                [row.email, row.source or "", row.note or "", row.created_at.isoformat()]
            )


if __name__ == "__main__":
    main()
