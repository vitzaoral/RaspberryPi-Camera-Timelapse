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
rpicam-hello
```

If command is not known, run:
```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y libcamera-apps
```

In my setup, I use the **Arducam 8MP IMX219 175 Degree Ultra Wide Angle Raspberry Pi Camera Module**. I noticed that images had a significant purple tint by default. To address this, I use a tuning file. You can download the tuning file `imx219_160d.json` and apply it when running `rpicam` commands. This resolves color issues and improves overall image quality.

Additional information can be found [here](https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/Lens-Shading/)

```bash
rpicam-still -o output.jpg --tuning-file /path/to/imx219_160d.json
```

Additional information about `rpicam` can be found [here](https://www.raspberrypi.com/documentation/computers/camera_software.html)

---

## 3. Install Required Packages
Install the necessary Python libraries and dependencies:
```bash
sudo apt update
sudo apt install python3-pil python3-opencv lsb-release -y
```

---

## 4. Install WittyPi 4 Mini
To install the WittyPi 4 Mini software:
1. Download and install the script:
   ```bash
   wget https://www.uugear.com/repo/WittyPi4/install.sh
   sudo sh install.sh
   ```
   Restart raspberry
   
2. Run WittyPi and setup
   ```bash
   pi@raspberrypi:~/wittypi $ ./wittyPi.sh
   ```

3. GPIO-4 pin doesn’t reach a stable status in given time (from manual) - edit daemon.sh on line 94:
   ```bash
   while [ $counter –lt 25 ]; do
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

[DietPi](https://dietpi.com/#downloadinfo) is recommended for its lightweight and faster performance compared to Raspberry Pi OS. Follow these steps to set it up:

## 1. Install OpenSSH Server
Install git with dietpi-software
Install the OpenSSH server to enable `scp` and SSH functionality:
```bash
sudo dietpi-software install openssh-server
sudo dietpi-software install git
```

On client:
  ```bash
  ssh root@192.168.11.246
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

4. Additionally, ensure that the camera is enabled in the system settings:
   - Open the DietPi configuration tool:
     ```bash
     dietpi-config
     ```
   - Navigate to `Display Options > RPi Camera` and set the camera to `[On]`.

5. After these steps, the system should properly detect and configure the camera. Skipping this configuration may result in the error:
   ```plaintext
   ERROR: rpi cam-apps currently only supports the raspberry pi platforms

## 3. Install rpicam Applications
Install `rpicam` and related tools:
```bash
sudo apt install rpicam-apps
```

## 4. Verify Camera Functionality
Test the camera functionality:
```bash
rpicam-hello
```

If you are using a non-original Arducam camera, such as the **Arducam 8MP IMX219 175 Degree Ultra Wide Angle Raspberry Pi Camera Module**, download and use the tuning file `imx219_160d.json`. Using this file helps correct significant color issues (e.g., purple tint) and improves image quality:

```bash
rpicam-still -o output.jpg --tuning-file /path/to/imx219_160d.json
```

Additional information about `rpicam` can be found [here](https://www.raspberrypi.com/documentation/computers/camera_software.html)

## 5. Install Python Libraries
Install required Python libraries:
```bash
sudo apt install python3-pil python3-requests python3-opencv
```

## 6. OTA
If you want update code over the air (OTA), you can do it with update_repository.py
So you have to git clone repository to the Raspberry

## 7. config.json
Define your **config.json** file in the root directory

```bash
{
    "camera_number": 2,
    "use_person_detection": true,
    "use_tuning_file": true,
    "cloudinary_url": "https://api.cloudinary.com/v1_1/xxx/image/upload",
    "cloudinary_upload_preset": "xxx",
    "blynk_temperature_auth": "xxx",
    "blynk_temperature_pin": "v23",
    "blynk_camera_auth": "xxx",
    "blynk_camera_deep_sleep_interval_pin": "v0",
    "blynk_camera_deep_sleep_interval_setted_pin": "v3",
    "blynk_camera_image_pin": "v1",
    "blynk_camera_wifi_signal_pin": "v6",
    "blynk_camera_version_pin": "v7",
    "blynk_camera_ip_pin": "v5",
    "blynk_camera_pin_current_time": "v8",
    "blynk_camera_pin_setted_working_time": "v9",
    "blynk_camera_pin_working_time": "v10",
    "blynk_camera_status_pin": "v13",
    "blynk_camera_human_detected_pin": "v18",
    "blynk_camera_next_start_time_pin": "v19",
    "blynk_camera_run_update_pin": "v20",
    "witty_pi_path": "/root/wittypi/",
    "repo_path": "/home/timelapse/"
}
```

## 8. final picture
![Schema](https://raw.githubusercontent.com/vitzaoral/RaspberryPi-Camera-Timelapse/master/camera/img/img.jpg)