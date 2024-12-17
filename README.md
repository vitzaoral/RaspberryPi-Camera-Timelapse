# RaspberryPi-Camera-Timelapse

## Overview

The **RaspberryPi-Camera-Timelapse** project is a low-power camera solution managed via the Blynk platform. It captures images at scheduled intervals, detects humans in the frame, overlays information such as timestamp and temperature, and uploads the enhanced images to Cloudinary. Power management is optimized using the Witty Pi 4 Mini for controlled sleep cycles, making it efficient for remote monitoring or time-lapse photography.

### Key Features
- **Scheduled Image Capture**: Configurable intervals for image capture, fully managed through Blynk.
- **Human Detection**: Real-time notification via Blynk if a human is detected in the image.
- **Cloud Upload**: Automatic image upload to Cloudinary for remote access.
- **Low Power**: Utilizes Witty Pi 4 Mini to control power, making it battery-friendly.

## Components

To replicate this project, you’ll need the following components:

- **Raspberry Pi Zero 2 WH**: The main processing unit, chosen for its small form factor and low power consumption.
- **Witty Pi 4 Mini**: A real-time clock and power management module that allows the Raspberry Pi to operate on a timed power cycle, greatly reducing power usage.
- **Raspberry Pi Camera Module V2**: The camera used for capturing images (Arducam 8MP IMX219 175 Degree)

## Getting Started

### Prerequisites
Make sure you have the following software and accounts set up:
1. **Python 3**: Installed on your Raspberry Pi.
2. **Blynk Account**: For remote monitoring and control.
3. **Cloudinary Account**: For uploading and storing captured images.
4. **SSH Access**: To deploy and manage your code on the Raspberry Pi remotely.

# Software Setup (Raspberry Pi OS)

## 1. Camera Configuration
To configure the camera, follow these steps:

1. Open the configuration file:
   ```bash
   sudo nano /boot/firmware/config.txt
   ```
2. Modify the following lines:
   - Find the line `camera_auto_detect=1` and update it to:
     ```plaintext
     camera_auto_detect=0
     ```
   - Find the line `[all]` and add this below it:
     ```plaintext
     dtoverlay=imx219
     ```
3. Save the file and reboot the system:
   ```bash
   sudo reboot
   ```

Refer to the [ArduCam IMX219 Camera Documentation](https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/8MP-IMX219/) for more details.

---

## 2. Verify Camera Functionality
To ensure the camera is working, run:
```bash
libcamera-hello
```

In my setup, I use the **Arducam 8MP IMX219 175 Degree Ultra Wide Angle Raspberry Pi Camera Module**. I noticed that images had a significant purple tint by default. To address this, I use a tuning file. You can download the tuning file `imx219_160d.json` and apply it when running `libcamera` commands. This resolves color issues and improves overall image quality.

Additional information can be found [here](https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/Lens-Shading/):

```bash
libcamera-still -o output.jpg --tuning-file /path/to/imx219_160d.json
```

---

## 3. Install Required Packages
Install the necessary Python libraries and dependencies:
```bash
sudo apt update
sudo apt install python3-pil python3-opencv
```

---

## 4. Install WittyPi 4 Mini
To install the WittyPi 4 Mini software:
1. Download and install the script:
   ```bash
   wget https://www.uugear.com/repo/WittyPi4/install.sh
   sudo sh install.sh
   ```

---

## 5. Manage `camera.service`
The `camera.service` file manages the automatic execution of the camera script.

### Create the service file
1. Open the service configuration file:
   ```bash
   sudo nano /etc/systemd/system/camera.service
   ```
2. Copy and paste your `camera.service` content into this file.

### Enable and start the service
1. Enable the service to run at startup:
   ```bash
   sudo systemctl enable camera.service
   ```
2. Start the service:
   ```bash
   sudo systemctl start camera.service
   ```

### Check the service status
To verify if the service is running:
```bash
sudo systemctl status camera.service
```

### View service logs
Use `journalctl` to check logs:
```bash
sudo journalctl -u camera.service
```

### Stop or disable the service
- To stop the service manually:
  ```bash
  sudo systemctl stop camera.service
  ```
- To disable the service at startup:
  ```bash
  sudo systemctl disable camera.service
  ```

---

# Software Setup (DietPi)

DietPi is recommended for its lightweight and faster performance compared to Raspberry Pi OS. Follow these steps to set it up:

## 1. Install OpenSSH Server
Install git with dietpi-software
Install the OpenSSH server to enable `scp` and SSH functionality:
```bash
sudo dietpi-software install openssh-server
```

## 2. Camera Configuration
To configure the camera:
1. Open the configuration file:
   ```bash
   sudo nano /boot/config.txt
   ```
2. Add or modify the following lines:
   ```plaintext
   camera_auto_detect=0
   dtoverlay=imx219
   ```
3. Save the file and reboot the system:
   ```bash
   sudo reboot
   ```

## 3. Install libcamera Applications
Install `libcamera` and related tools:
```bash
sudo apt install libcamera-apps
```

## 4. Verify Camera Functionality
Test the camera functionality:
```bash
libcamera-hello
```

If you are using a non-original Arducam camera, such as the **Arducam 8MP IMX219 175 Degree Ultra Wide Angle Raspberry Pi Camera Module**, download and use the tuning file `imx219_160d.json`. Using this file helps correct significant color issues (e.g., purple tint) and improves image quality:

```bash
libcamera-still -o output.jpg --tuning-file /path/to/imx219_160d.json
```

## 5. Install Python Libraries
Install required Python libraries:
```bash
sudo apt install python3-pil python3-opencv
```
