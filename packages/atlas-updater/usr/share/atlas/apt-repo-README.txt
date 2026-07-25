Copy the built tree from dist/apt-repo onto the appliance as /srv/atlas/apt-repo
or onto USB as atlas-apt-repo/, then enable with:

  sudo python3 /usr/lib/atlas/atlas-os-apt.py enable-source /srv/atlas/apt-repo

See docs/updates/OS_UPDATES.md and scripts/build-apt-repo.sh.
