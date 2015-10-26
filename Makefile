all:
	@echo "Héllo you!"


copy-static:
	cp -rf static build/

build-html:
	rm build -rf || true
	python sotoki.py build templates/ db/superuser/ build/

build-all: build-html copy-static

load:
	rm -rf db/superuser/* || true
	mkdir -p db/superuser/
	python sotoki.py load dumps/superuser/ db/superuser

serve:
	cd build/ && python3 -m http.server
