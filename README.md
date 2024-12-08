# RaspberryPi-Camera-Timelapse

# 🚧 In progress! 🚧

## Overview

The **RaspberryPi-Camera-Timelapse** project is a low-power camera solution that captures images at scheduled intervals, uses human detection to trigger notifications, and uploads images to the Cloudinary platform for easy access. This setup leverages the Witty Pi 4 Mini to control power cycles, allowing for a highly energy-efficient operation, ideal for time-lapse photography or remote monitoring applications. 

### Key Features
- **Scheduled Image Capture**: Configurable intervals for image capture, fully managed through Blynk.
- **Human Detection**: Real-time notification via Blynk if a human is detected in the image.
- **Cloud Upload**: Automatic image upload to Cloudinary for remote access.
- **Low Power**: Utilizes Witty Pi 4 Mini to control power, making it battery-friendly.

## Components

To replicate this project, you’ll need the following components:

- **Raspberry Pi Zero WH**: The main processing unit, chosen for its small form factor and low power consumption.
- **Witty Pi 4 Mini**: A real-time clock and power management module that allows the Raspberry Pi to operate on a timed power cycle, greatly reducing power usage.
- **Raspberry Pi Camera Module V2**: The camera used for capturing images.

## Getting Started

### Prerequisites
Make sure you have the following software and accounts set up:
1. **Python 3**: Installed on your Raspberry Pi.
2. **Blynk Account**: For remote monitoring and control.
3. **Cloudinary Account**: For uploading and storing captured images.
4. **SSH Access**: To deploy and manage your code on the Raspberry Pi remotely.

### Software Setup
= nastaveni kamery
sudo nano /boot/firmware/config.txt 
#Find the line: camera_auto_detect=1, update it to:
camera_auto_detect=0
#Find the line: [all], add the following item under it:
dtoverlay=imx219
#Save and reboot.
https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/8MP-IMX219/

- pusteni kamery ze jede
run libacamera-hello

= instalace dalsich balicku
sudo apt update
sudo apt install python3-pil
sudo apt install python3-opencv

= instalace WittyPi4 Mini
wget https://www.uugear.com/repo/WittyPi4/install.sh
sudo sh install.sh



1. **Clone the Repository**:
   ```bash
   git clone https://github.com/yourusername/RaspberryPi-Camera-Timelapse.git
   cd RaspberryPi-Camera-Timelapse
