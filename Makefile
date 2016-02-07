all:
	@echo "Héllo you!"


copy-static:
	cp -rf static work/output

clean:
	rm work/output -rf || true

serve:
	cd work/output && python3 -m http.server
