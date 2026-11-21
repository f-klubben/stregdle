# Stregsystemdle

The daily product-guessing game ("-dle") for the F-Klub stregsystem, running as
its own project.

It was originally an app inside the stregsystemet Django project. It now lives
here so it cannot bloat that project: there are no ORM models, no migrations and
no imports from `stregsystem`. Everything it knows about the shop comes from a
handful of read-only `SELECT`s against the stregsystem database.

## How it talks to the stregsystem

| Read from                     | What for                                        |
| ----------------------------- | ----------------------------------------------- |
| `stregsystem_product`         | id, name, price, alcohol, caffeine              |
| `stregsystem_category`        | category names (via `stregsystem_product_categories`) |
| `stregsystem_room`            | room names (via `stregsystem_product_rooms`)    |
| `stregsystem_namedproduct`    | short names ("alias") used by search            |
| `stregsystem_sale`            | sales of the last 90 days and in total          |

Those are Django's default table names for the stregsystem app, so they survive
as long as that project's models keep their names. The queries live in one
place: `productdle/repository.py`.

Run `python manage.py dbcheck` after deploying or after a schema change - it
executes the same queries and reports what came back.

### Use a read-only database user

The game only ever reads, so give it an account that can only read:

```sql
CREATE USER 'stregdle'@'%' IDENTIFIED BY '<password>';
GRANT SELECT ON stregsystem.* TO 'stregdle'@'%';
```

## Configuration

Everything is set through environment variables:

| Variable               | Default                        | Meaning                                          |
| ---------------------- | ------------------------------ | ------------------------------------------------ |
| `STREG_DB_HOST`        | `127.0.0.1`                    | MySQL/MariaDB host                               |
| `STREG_DB_PORT`        | `3306`                         | Port                                             |
| `STREG_DB_NAME`        | `stregsystem`                  | Database name                                    |
| `STREG_DB_USER`        | `stregdle`                     | Read-only user                                   |
| `STREG_DB_PASSWORD`    | (empty)                        | Password                                         |
| `STREGSYSTEM_URL`      | `http://localhost:8000/`       | Where the header's Menu/Genstart buttons point   |
| `STREGDLE_SOURCE_URL`  | (unset)                        | Source link in the footer; omitted when unset    |
| `STREGDLE_STATS_DIR`   | `<checkout>/var`               | Where the day's guess tally is written; empty disables it |
| `STREGDLE_SECRET_KEY`  | dev key                        | Set a real one in production                     |
| `STREGDLE_ALLOWED_HOSTS` | `localhost,127.0.0.1`        | Comma-separated host names                       |
| `STREGDLE_HTTPS`       | (off)                          | `1` when served over HTTPS (enables redirect, HSTS and secure cookies) |
| `STREGDLE_HSTS_SECONDS` | `31536000` when HTTPS is on   | HSTS lifetime                                    |
| `STREGDLE_DEBUG`       | (off)                          | `1` for Django debug mode                        |

Product data is cached in-process for 60 seconds, so the shop's database is read
at most once a minute per worker regardless of how many people play.

## Running it

```sh
uv sync                                  # or: python -m venv .venv && pip install -e .
python manage.py dbcheck                 # verify the SQL against the database
python manage.py runserver               # development
```

## Deploying

The game follows the stregsystem's own layout: a checkout under `/data`, its own
virtualenv, gunicorn on a local port, systemd for the process, and the reverse
proxy for TLS and `/static/` (fklub runs Caddy; `deploy/` holds a Caddy site
block and an nginx one). Adjust the paths, the user, the port and the host name
if they differ on the server.

```sh
# 1. Account and checkout
sudo useradd --system --home /data/stregdle --shell /usr/sbin/nologin stregdle
sudo -u stregdle git clone <repo-url> /data/stregdle
cd /data/stregdle

# 2. Virtualenv with the app and gunicorn (Python 3.11, like production)
sudo -u stregdle python3.11 -m venv venv
sudo -u stregdle venv/bin/pip install --upgrade pip
sudo -u stregdle venv/bin/pip install '.[prod]'

# 3. Configuration
sudo -u stregdle cp deploy/stregdle.env.example stregdle.env
sudo -u stregdle chmod 600 stregdle.env
sudo -u stregdle "$EDITOR" stregdle.env        # secret key, host name, DB password
set -a; . ./stregdle.env; set +a
sudo install -d -o stregdle -g stregdle /data/stregdle/var

# 4. Check the database and the photos, then build the static files
sudo -u stregdle venv/bin/python manage.py dbcheck
sudo -u stregdle venv/bin/python manage.py wares
sudo -u stregdle venv/bin/python manage.py check --deploy
sudo -u stregdle venv/bin/python manage.py collectstatic --noinput

# 5. Service
sudo cp deploy/stregdle.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now stregdle
curl -s http://127.0.0.1:8001/healthz        # {"status": "ok"}

# 6. Reverse proxy - Caddy on fklub (nginx alternative in deploy/nginx.conf)
#    Append deploy/caddy.conf to /srv/infra/caddy/Caddyfile after taking a backup.
sudo cp -a /srv/infra/caddy/Caddyfile /root/Caddyfile.bak-$(date +%F)
#    ... append the site block, then:
sudo caddy validate --config /srv/infra/caddy/Caddyfile --adapter caddyfile
sudo caddy reload --config /srv/infra/caddy/Caddyfile --adapter caddyfile
```

### What fklub actually runs

- Ubuntu 18.04, so the virtualenv comes from `/usr/local/bin/python3.11` (3.11.9).
- `/data/stregdle` owned by the system user `stregdle`; gunicorn on
  `127.0.0.1:8001`, run by `stregdle.service`, as in `deploy/stregdle.service`.
- Caddy terminates TLS for `stregdle.fklub.dk` and proxies to that port; the site
  block is the one in `deploy/caddy.conf`, added to `/srv/infra/caddy/Caddyfile`.
  Caddy issues and renews the certificate itself.
- The read-only MySQL account was created with the server's admin credentials:
  `sudo mysql --defaults-file=/etc/mysql/debian.cnf -e "CREATE USER ... /* SELECT only */"`.
- Static files: `collectstatic` writes `/data/stregdle/staticfiles`, which Caddy
  serves under `/static/` with a 30 day cache.

### Cutting over at midnight

A change that alters the game itself - the columns, the scoring, the answer pool -
must not land in the middle of a day: players are mid-board. Deploy it in two
halves:

1. Leave the running checkout alone and push the new release to `main`.
2. Install the cutover timer for the coming midnight:

```sh
sudo install -m 755 deploy/cutover.sh /usr/local/sbin/stregdle-cutover.sh
sudo install -m 644 deploy/stregdle-cutover.service deploy/stregdle-cutover.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now stregdle-cutover.timer
systemctl list-timers stregdle-cutover.timer --no-pager
```

At 00:00 the timer pulls `main`, reinstalls, runs `collectstatic`, restarts the
service and removes itself. `Persistent=true` catches up if the server was down
at that moment. Ordinary changes (a photo, a typo, docs) need none of this.

`manage.py check --deploy` must report no issues before you start the service;
it flags a weak secret key and missing HTTPS settings. Note that `collectstatic`
has to run again whenever the ware photos change.

Updating:

```sh
cd /data/stregdle
sudo -u stregdle git pull --ff-only
sudo -u stregdle venv/bin/pip install '.[prod]'
sudo -u stregdle venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart stregdle
```

The app writes nothing itself except the guess tally in `STREGDLE_STATS_DIR`
(and `staticfiles/`, during `collectstatic`), so the only other persistent state
on the host is the checkout.

## The statistics page

`/statistics/` shows the day's game in numbers, for a screen standing next to the
fridge: participants, total guesses, how many found the product, how many gave
up, and the average number of attempts. Two charts break it down - attempts used
by those who found it, and guesses per hour. It reuses the game's header and
footer and refreshes itself every minute.

It shows counts only. The answer, the guessed products and the per-guess colours
never appear there, because the screen is public and would spoil the round for
whoever is still playing.

Counting works without sessions or a database: every guess appends one line to
`<STREGDLE_STATS_DIR>/<date>.jsonl` (`os.write` on an `O_APPEND` file, so the
gunicorn workers can share it), and the board aggregates that file when it
renders. The page keeps a random id in `localStorage` and sends it along with
its guesses, which is what makes "participants" countable; it identifies nobody
and nothing else stores it. The files are small and can be deleted once nobody
cares about the history; a failed write is logged and never breaks a guess.

## The game rules

One product is the answer each day. The picks are deterministic per date (seeded
`stregdle-<date>`), the same seed the in-app version used, so moving the game
here did not change the answer of the day. Guesses are compared attribute by
attribute: price, alcohol, caffeine, sales and total are directional ("higher" /
"lower"), while a shared category or room counts as a match.

## Ware photos

The photos in `productdle/static/productdle/wares/` came out of
`Køleskabsfordeling 2025 April.xlsx` (the fridge planograms), one per ware. The
name each photo answers to is listed in `productdle/wares.py`; markup, casing,
accents and punctuation are ignored, and the most specific name wins, so a
"Faxe Kondi Booster Melon Boost" never gets the plain "Faxe Kondi" picture.

After the shop's product list changes, run this against the database to see
which products still have no photo and which photos match nothing:

```sh
python manage.py wares
```

Add an alias in `productdle/wares.py` for each missing product (or drop the
photo if the ware is gone).

## Tests

```sh
python manage.py test
```

The game logic is tested against plain `Product` objects, so the suite needs no
database.

## Provenance

The game logic, page and stylesheet started life in the stregsystemet project
(`productdle/` there, which has been removed). `productdle/static/productdle/stregsystem.css`
is that project's `stregsystem.css`, copied verbatim so the page keeps the
stregsystem look; it is covered by the Limfjords-Porter-Ware licence.
