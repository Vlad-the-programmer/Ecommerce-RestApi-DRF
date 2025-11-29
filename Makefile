# Makefile for Django project management

# Run Django makemigrations and migrate
mmm:
	docker exec ecommerce_api python manage.py makemigrations
	docker exec ecommerce_api python manage.py migrate

# Run only makemigrations
mm:
	docker exec ecommerce_api python manage.py makemigrations

# Run only migrate
m:
	docker exec ecommerce_api python manage.py migrate

# Run Django shell
shell:
	docker exec -it ecommerce_api python manage.py shell

# Run Django shell_plus if installed
shell_plus:
	docker exec -it ecommerce_api python manage.py shell_plus

# Run Django development server
runserver:
	docker exec -it ecommerce_api python manage.py runserver 0.0.0.0:8000

# Run tests
test:
	docker exec ecommerce_api python manage.py test

# Show migrations
showmigrations:
	docker exec ecommerce_api python manage.py showmigrations

# Create superuser (interactive)
createsuperuser:
	docker exec -it ecommerce_api python manage.py createsuperuser

pytest_unit:
	docker exec ecommerce_api pytest tests/unit

uv_export:
	uv export > requirements.txt

