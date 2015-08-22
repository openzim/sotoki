all:
	@echo "Héllo you!"


copy-static:
	cp -r static build/


build-html:
	rm build -rf || true
	python sotoki.py build templates/ db/superuser/ build/

build-all: build-html copy-static


load:
	rm -r db/superuser || true
	python sotoki.py load dumps/superuser/ db/superuser

serve:
	cd build/ && python3 -m http.server
