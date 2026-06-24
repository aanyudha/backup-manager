<?php
$servername = "192.168.1.55";
$username = "root";
$password = "Micros321";
$database = "pcinventory";

$conn = new mysqli($servername, $username, $password, $database);

if ($conn->connect_error) {
    die("Koneksi Gagal: " . $conn->connect_error);
}
?>
