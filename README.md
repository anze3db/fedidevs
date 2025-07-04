# Fedidevs

This is the source code for the [fedidevs.com](https://fedidevs.com) website.

## Set up dev environment

0. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)

1. Run the migrations
```
uv run python manage.py migrate
```

2. Run the development server
```
uv run python manage.py runserver
```

3. In a separate terminal set up tailwindcss...
```
uv run python manage.py tailwind install
```

4. ... and start the tailwind server
```
uv run python manage.py tailwind start
```

5. [optional] ... and start the background worker (only needed for syncing followers on login)
```
uv run python manage.py rundramatiq --reload
```

6. [optional] Populate the local database (takes about ~1hr)
```
uv run python manage.py scheduler --run-now
```

or run the crawler and indexer separately if you only want to populate account data (takes about ~5mins)

```
uv run python manage.py crawler
uv run python manage.py indexer
```

7. [optional] Create a Django Admin user for `http://localhost:8000/admin`
```
uv run python manage.py createsuperuser
```

