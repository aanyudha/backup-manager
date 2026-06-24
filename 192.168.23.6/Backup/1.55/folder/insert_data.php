<style>
    .success-message {
        background-color: #4CAF50;
        color: white;
        padding: 10px;
        border-radius: 5px;
        text-align: center;
        margin-bottom: 10px;
		font-size:18;
    }

    .back-button {
        background-color: #007bff;
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 5px;
        text-decoration: none;
        text-align: center;
        display: inline-block;
        margin-right: 10px;
		align:center;
    }

    .back-button:hover {
        background-color: #0056b3;
    }
</style>


<?php
include 'koneksi.php'; // Sertakan file koneksi

if ($_SERVER["REQUEST_METHOD"] == "POST") {
    $device = $_POST['device'];
    $device_brand = $_POST['device_brand'];
    $device_sn = $_POST['device_sn'];
    $processor = $_POST['processor'];
    $hardisk = $_POST['hardisk'];
    $ram = $_POST['ram'];
    $windows_version = $_POST['windows_version'];
    $windows_sn = $_POST['windows_sn'];
    $office_version = $_POST['office_version'];
    $office_sn = $_POST['office_sn'];
    $antivirus = $_POST['antivirus'];
    $ip_address = $_POST['ip_address'];
	$pcname = $_POST['pcname'];
    $dept = $_POST['dept'];
    $staff = $_POST['staff'];
    $vendor = $_POST['vendor'];
    $purchase_year = $_POST['purchase_year'];
    $status = $_POST['status'];

    $sql = "INSERT INTO pcinventory (device, device_brand, device_sn,processor, hardisk, ram, windows_version,windows_sn, office_version, office_sn, antivirus, ip_address,pcname, vendor, purchase_year, status,dept,staff) VALUES ('$device', '$device_brand','$device_sn', '$processor', '$hardisk', '$ram', '$windows_version','$windows_sn', '$office_version','$office_sn', '$antivirus', '$ip_address','$pcname', '$vendor', '$purchase_year', '$status','$dept','$staff')";

  if ($conn->query($sql) === TRUE) {
        echo '<div class="success-message">Data berhasil disimpan!</div>';
        echo '<center><a class="back-button" href="index.php">BACK</a></center>';
    } else {
        echo "Error: " . $sql . "<br>" . $conn->error;
    }
}

$conn->close();
?>
