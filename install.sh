echo "[Seat:*]\ngreeter=lightdm-gtk-greeter\nuser-session=pillarium" > /etc/lightdm/lightdm.conf
sudo update-desktop-databases
sudo apt install python3 python3-pip python3-venv
sudo apt update
sudo apt upgrade
python3 -m venv .venv
wait
. .venv/bin/activate
pip3 install -r requirements.txt
echo "Installed Pillarium successfully!"