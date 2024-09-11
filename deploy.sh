TARGET_DIR=/opt/smser

sudo rm -r "${TARGET_DIR}"/smser
sudo cp -r smser "${TARGET_DIR}"/smser
sudo cp pyproject.toml "${TARGET_DIR}"
sudo chown -R smser:smser "${TARGET_DIR}"
sudo -u smser "${TARGET_DIR}"/.venv/bin/pip install -e "${TARGET_DIR}"
