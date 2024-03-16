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

3. Run the migrations
```
python manage.py migrate
```

4. Run the development server
```
python manage.py runserver
```

5. Populate the local database (takes about ~2hrs)
```
python manage.py scheduler --run-now
```

6. Create a Django Admin user for `http://localhost:8000/admin`
```
python manage.py createsuperuser
```
