all:
	@echo "Héllo you!"


copy-static:
	cp -r static build/


build-html:
	rm build -rf || true
	LD_PRELOAD=/usr/local/lib/libwiredtiger.so python sotoki.py build templates/ db/superuser/ build/

build-all: build-html copy-static


load:
	rm -r db/superuser || true
	LD_PRELOAD=/usr/local/lib/libwiredtiger.so python sotoki.py load dumps/superuser/ db/superuser

serve:
	cd build/ && python3 -m http.server
