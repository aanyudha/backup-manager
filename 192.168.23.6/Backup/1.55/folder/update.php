<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
</head>


<body>
<div class="container">
    <?php
    include 'koneksi.php';
    if ($_SERVER["REQUEST_METHOD"] == "POST" && isset($_POST['id'])) {
        $id = $_POST['id'];
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
		$vendor = $_POST['vendor'];
		$purchase_year = $_POST['purchase_year'];
		$dept = $_POST['dept'];
		$staff = $_POST['staff'];
		$status = $_POST['status'];

		// Query SQL untuk memperbarui data dalam tabel pcinventory
		$sql = "UPDATE pcinventory
            SET device='$device', device_brand='$device_brand', device_sn='$device_sn', 
                processor='$processor', hardisk='$hardisk', ram='$ram',
                windows_version='$windows_version', windows_sn='$windows_sn', 
                office_version='$office_version', office_sn='$office_sn',
                antivirus='$antivirus', ip_address='$ip_address', pcname='$pcname', 
                vendor='$vendor', purchase_year='$purchase_year', status='$status',  dept='$dept',  staff='$staff' 
            WHERE id = $id";

        if (mysqli_query($conn, $sql)) {
            echo '<center><div class="alert alert-success" role="alert">Data berhasil diperbarui.</div>';
            echo '<a class="btn btn-primary" href="report.php">Back to Report</a></center>';
        } else {
            echo '<div class="alert alert-danger" role="alert">Terjadi kesalahan saat memperbarui data: ' . mysqli_error($conn) . '</div>';
        }
    } else {
        echo "Permintaan tidak valid.";
    }
    mysqli_close($conn);
    ?>
</div>
</body>
</html>
