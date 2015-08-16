all:
	@echo "Héllo you!"


generate:
	rm build -rf || true
	python sotoki.py build templates/ db/superuser/ build/
	cp -r static build/

load:
	rm -r db/superuser || true
	python sotoki.py load dumps/superuser/ db/superuser

serve:
	cd build/ && python3 -m http.server
