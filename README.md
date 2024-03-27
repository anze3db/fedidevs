# Fedidevs

This is the source code for the [fedidevs.com](https://fedidevs.com) website.

## Set up dev environment

0. Install Python 3.12
1. Create a venv environment
```
python -m venv .venv
```

2. Activate the virtual env
```
. .venv/bin/activate
```

3. Install required packages
```
python -m pip install -r requirements.txt
```

4. Run the migrations
```
python manage.py migrate
```

5. Run the development server
```
python manage.py runserver
```

6. In a separate terminal set up tailwindcss...
```
python manage.py tailwind install
```

7. ... and start the tailwind server
```
python manage.py tailwind start
```

8. Populate the local database (takes about ~1hr)
```
python manage.py scheduler --run-now
```

or run the crawler and indexer separately if you only want to populate account data (takes about ~5mins)

```
python manage.py crawler
python manage.py indexer
```

9. Create a Django Admin user for `http://localhost:8000/admin`
```
python manage.py createsuperuser
```
