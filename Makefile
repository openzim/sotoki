all:
	@echo "Héllo you!"


copy-static:
	cp -rf static build/

clean:
	rm build -rf || true

build-html:
	python sotoki.py offline db/superuser build/
	python sotoki.py render templates/ db/superuser/ build/

build-all: clean build-html copy-static

load:
	rm -rf db/superuser/* || true
	mkdir -p db/superuser/
	python sotoki.py load dumps/superuser/ db/superuser

serve:
	cd build/ && python3 -m http.server
