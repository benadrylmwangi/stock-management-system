# Django MySQL Integration

This project was originally configured with SQLite; the following steps set up a MySQL database backend.  

## 1. Install MySQL server

Make sure a MySQL server (or compatible: MariaDB) is running on your system or accessible remotely.  
Create a database and user, for example:

```sql
CREATE DATABASE mysite CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'mysiteuser'@'localhost' IDENTIFIED BY 'supersecret';
GRANT ALL PRIVILEGES ON mysite.* TO 'mysiteuser'@'localhost';
FLUSH PRIVILEGES;
```

Adjust the credentials as needed.

## 2. Configure Django

The `mysite/settings.py` file now contains a MySQL configuration block. It reads connection details from environment variables, so you can set them in your shell or `.env` file:

```bash
export MYSQL_DATABASE=mysite
export MYSQL_USER=mysiteuser
export MYSQL_PASSWORD=supersecret
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
```

For Windows PowerShell use `setx` or `$Env:` assignments.  

## 3. Install dependencies

Activate your virtual environment (e.g. `dj\Scripts\Activate.ps1`), then:

```bash
pip install -r requirements.txt
```

`mysqlclient` is required to talk to MySQL; this will install the proper Python bindings.

## 4. Apply migrations

Run Django management commands to create the tables in MySQL:

```bash
python manage.py migrate
```

If you were migrating data from SQLite, dump it and load it into MySQL using `dumpdata`/`loaddata`.

## 5. Run the server

```bash
python manage.py runserver
```

Your app will now use the MySQL backend.

---

> ⚠️ Keep `DEBUG=False` and configure `ALLOWED_HOSTS` before deploying to production.  
> 🚫 Do **not** commit your real database credentials; use environment variables or secrets management.