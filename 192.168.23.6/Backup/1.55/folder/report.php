<?php
include 'koneksi.php'; 

$totalCount = 0;
$where = "1";  // Default condition to retrieve all records

if (isset($_GET['dept']) && !empty($_GET['dept'])) {
    $dept = $conn->real_escape_string($_GET['dept']);
    if ($dept !== "All") {
        $where .= " AND dept = '$dept'";
    }
}

if (isset($_GET['device']) && !empty($_GET['device'])) {
    $device = $conn->real_escape_string($_GET['device']);
    $where .= " AND device = '$device'";
}

$sql = "SELECT * FROM pcinventory WHERE $where";
$result = $conn->query($sql);

$totalCount = $result->num_rows; // Get the total count

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PC Inventory Report</title>

    <!-- Add the Bootstrap CSS link -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">

    <style>
        /* Add custom CSS here if needed */
        .inventory-table {
            margin-top: 20px;
        }
		.menu {
            margin-bottom: 20px;
            text-align: right;
        }
        .menu a {
            text-decoration: none;
            color: #fff;
            background-color: #4CAF50;
            border: none;
            border-radius: 4px;
            padding: 10px 20px;
            cursor: pointer;
            display: inline-block;
        }
        .menu a:hover {
            background-color: #45a049;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mt-4 mb-4"> Report</h1>
		<div class="menu">
			<a href="index.php">NEW INVENTORY</a>
		</div>
        <form action="report.php" method="get">
            <div class="row mb-3">
                <div class="col-md-3">
                    <label for="dept" class="form-label">Filter by Department:</label>
                    <select name="dept" id="dept" class="form-select">
                        <option value="">All</option>
						<option value="Engineering">Engineering</option>
						<option value="FB">FB</option>
						<option value="Finance">Finance</option>
						<option value="GM">GM</option>
						<option value="Housekeeping">Housekeeping</option>
						<option value="HRD">HRD</option>
						<option value="Reservation">Reservation</option>
						<option value="Room">Room</option>
						<option value="Sales">Sales</option>
                    </select>
                </div>

                <div class="col-md-3">
                    <label for="device" class="form-label">Filter by Device:</label>
                    <select name="device" id="device" class="form-select">
                        <option value="">All</option>
                    </select>
                </div>

                <div class="col-md-2">
                    <label>&nbsp;</label>
                    <button type="submit" class="btn btn-primary form-control">Filter</button>
                </div>
				<p>Total items: <?php echo $totalCount; ?></p>
            </div>
        </form>

        <table class="table table-bordered table-striped inventory-table">
            <thead class="table-dark">
                <tr>
					<th>EDIT</th>
                    <th>ID</th>
                    <th>Device</th>
                    <th>Device Brand</th>
                    <th>Device SN</th>
                    <th>Processor</th>
                    <th>Hardisk</th>
                    <th>RAM</th>
                    <th>Windows Version</th>
                    <th>Windows SN</th>
                    <th>Office Version</th>
                    <th>Office SN</th>
                    <th>Antivirus</th>
                    <th>IP Address</th>
					<th>PC Name</th>
                    <th>Dept</th>
                    <th>Staff</th>
                    <th>Vendor</th>
                    <th>Purchase Year</th>
                    <th>Status</th>
                </tr>
            </thead>
		 <tbody>

        <?php
        if ($result->num_rows > 0) {
            while ($row = $result->fetch_assoc()) {
                echo "<tr>";
				echo "<td><a href='edit.php?id=" . $row['id'] . "'>Edit</a></td>";
                echo "<td>" . $row['id'] . "</td>";
                echo "<td>" . $row['device'] . "</td>";
                echo "<td>" . $row['device_brand'] . "</td>";
                echo "<td>" . $row['device_sn'] . "</td>";
                echo "<td>" . $row['processor'] . "</td>";
                echo "<td>" . $row['hardisk'] . "</td>";
                echo "<td>" . $row['ram'] . "</td>";
                echo "<td>" . $row['windows_version'] . "</td>";
                echo "<td>" . $row['windows_sn'] . "</td>";
                echo "<td>" . $row['office_version'] . "</td>";
                echo "<td>" . $row['office_sn'] . "</td>";
                echo "<td>" . $row['antivirus'] . "</td>";
                echo "<td>" . $row['ip_address'] . "</td>";
			    echo "<td>" . $row['pcname'] . "</td>";
                echo "<td>" . $row['dept'] . "</td>";
                echo "<td>" . $row['staff'] . "</td>";
                echo "<td>" . $row['vendor'] . "</td>";
                echo "<td>" . $row['purchase_year'] . "</td>";
                echo "<td>" . $row['status'] . "</td>";
                echo "</tr>";
		 
            }
        } else {
            echo "<tr><td colspan='18'>No records found.</td></tr>";
        }
        ?>
		     </tbody>
    </table>

  </div>
<script>
document.addEventListener("DOMContentLoaded", function () {
    filterDeviceOptions(); // Run this function initially to populate the device dropdown.

    document.getElementById("dept").addEventListener("change", function () {
        filterDeviceOptions(); // Run this function when the department dropdown changes.
    });
});

function filterDeviceOptions() {
    var selectedDept = document.getElementById("dept").value;
    var deviceSelect = document.getElementById("device");

    // Clear existing options
	deviceSelect.innerHTML = ''; // Remove the default "All" option

    // Define device options based on the selected department
    var deviceOptions = {
		"All": ["","Laptop", "PC", "Server", "Printer", "Scanner", "Monitor", "UPS", "Micros", "Micros Printer"],
        "Engineering": ["","Laptop", "PC", "Server", "Printer", "Scanner", "Monitor", "UPS", "Micros", "Micros Printer"],
		"FB": ["","Laptop", "PC", "Server", "Printer", "Scanner", "Monitor", "UPS", "Micros", "Micros Printer"],
		"Finance": ["","Laptop", "PC", "Server", "Printer", "Scanner", "Monitor", "UPS", "Micros", "Micros Printer"],
		"GM": ["","Laptop", "PC", "Server", "Printer", "Scanner", "Monitor", "UPS", "Micros", "Micros Printer"],
		"Housekeeping": ["","Laptop", "PC", "Server", "Printer", "Scanner", "Monitor", "UPS", "Micros", "Micros Printer"],
		"HRD": ["","Laptop", "PC", "Server", "Printer", "Scanner", "Monitor", "UPS", "Micros", "Micros Printer"],
		"Reservation": ["","Laptop", "PC", "Server", "Printer", "Scanner", "Monitor", "UPS", "Micros", "Micros Printer"],
		"Room": ["","Laptop", "PC", "Server", "Printer", "Scanner", "Monitor", "UPS", "Micros", "Micros Printer"],
		"Sales": ["","Laptop", "PC", "Server", "Printer", "Scanner", "Monitor", "UPS", "Micros", "Micros Printer"],
    };


    var options = deviceOptions[selectedDept] || deviceOptions["All"]; // Use "All" options when selectedDept is undefined

    options.forEach(function (device) {
        var option = document.createElement("option");
        option.text = device;
        option.value = device;
        deviceSelect.add(option);
    });
}
</script>

</body>
</html>
