<!DOCTYPE html>
<html>
<head>
    <title>Edit PC Inventory</title>
	<meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f5f5f5;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }

        .container {
            background: #fff;
            border: 1px solid #ccc;
            border-radius: 5px;
            box-shadow: 0px 0px 10px #aaa;
            width: 80%;
            max-width: 600px;
            padding: 20px;
        }

        .container h2 {
            text-align: center;
        }

        .form-group {
            display: flex;
            flex-direction: column;
            margin-bottom: 20px;
        }

        .form-group label {
            font-weight: bold;
            margin-bottom: 5px;
        }

        .form-group input, .form-group select {
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 16px;
        }

        .form-group input[type="submit"] {
            background-color: #4CAF50;
            color: #fff;
            border: none;
            border-radius: 4px;
            padding: 10px 20px;
            cursor: pointer;
            font-size: 18px;
            text-align: center;
        }

        .form-group input[type="submit"]:hover {
            background-color: #45a049;
        }

        .back-link {
            text-align: center;
            margin-top: 20px;
        }

        .back-link a {
            text-decoration: none;
            color: #333;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>Edit PC Inventory Entry</h2>

        <?php
        if (isset($_GET['id'])) {
            $id = $_GET['id'];
            include 'koneksi.php';

            $sql = "SELECT * FROM pcinventory WHERE id = $id";
            $result = mysqli_query($conn, $sql);

            if (mysqli_num_rows($result) == 1) {
                $row = mysqli_fetch_assoc($result);

                echo '<form action="update.php" method="POST">';
                echo '<input type="hidden" name="id" value="' . $row['id'] . '">';

                foreach ($row as $column => $value) {
                    if ($column != 'id') {
                        echo '<div class="form-group">';
                        echo '<label for="' . $column . '">' . strtoupper($column) . ':</label>';

                        if ($column == 'device') {
                            // Create a dropdown menu for the "Device" field
                            echo '<select name="' . $column . '">';
                            echo '<option value="PC" ' . ($value == 'PC' ? 'selected' : '') . '>PC</option>';
                            echo '<option value="Laptop" ' . ($value == 'Laptop' ? 'selected' : '') . '>Laptop</option>';
                            echo '<option value="Monitor" ' . ($value == 'Monitor' ? 'selected' : '') . '>Monitor</option>';
                            echo '<option value="UPS" ' . ($value == 'UPS' ? 'selected' : '') . '>UPS</option>';
                            echo '<option value="Printer" ' . ($value == 'Printer' ? 'selected' : '') . '>Printer</option>';
							echo '<option value="Scanner" ' . ($value == 'Scanner' ? 'selected' : '') . '>Scanner</option>';
							echo '<option value="Encoder" ' . ($value == 'Encoder' ? 'selected' : '') . '>Encoder</option>';
							echo '<option value="Micros" ' . ($value == 'Micros' ? 'selected' : '') . '>Micros</option>';
							echo '<option value="Micros Printer" ' . ($value == 'Micros Printer' ? 'selected' : '') . '>Micros Printer</option>';
                            echo '</select>';
                        } elseif ($column == 'windows_version') {
                            // Create a dropdown menu for the "windows_version" field
                            echo '<select name="' . $column . '">';
                            $windowsVersions = array(
								'-',
                                'Windows 7',
                                'Windows 10',
                                'Windows 11',
                                'Windows Server 2003',
                                'Windows Server 2008',
                                'Windows Server 2012',
                                'Windows Server 2019',
                                'Linux'
                            );
                            foreach ($windowsVersions as $option) {
                                echo '<option value="' . $option . '" ' . ($value == $option ? 'selected' : '') . '>' . $option . '</option>';
                            }
                            echo '</select>';
						 } elseif ($column == 'dept') {
                            // Create a dropdown menu for the "dept" field
                            echo '<select name="' . $column . '">';
                            $dept = array(
                                'Engineering',
                                'FB',
                                'Finance',
                                'GM',
                                'Housekeeping',
                                'HRD',
                                'Reservation',
                                'Room',
								'Sales'
                            );
                            foreach ($dept as $option) {
                                echo '<option value="' . $option . '" ' . ($value == $option ? 'selected' : '') . '>' . $option . '</option>';
                            }
                            echo '</select>';
							
                        } elseif ($column == 'status') {
                            // Create a dropdown menu for the "status" field
                            echo '<select name="' . $column . '">';
                            echo '<option value="Active" ' . ($value == 'Active' ? 'selected' : '') . '>Active</option>';
                            echo '<option value="Not Active" ' . ($value == 'Not Active' ? 'selected' : '') . '>Not Active</option>';
                            echo '</select>';
                        } else {
                            // Create regular text input fields for other columns
                            echo '<input type="text" name="' . $column . '" value="' . $value . '">';
                        }

                        echo '</div>';
                    }
                }
          
                echo '<div class="form-group">';
                echo '<input type="submit" value="Update">';
                echo '</div>';
                echo '</form>';
            } else {
                echo "PC inventory entry not found.";
            }

            mysqli_close($conn);
        } else {
            echo "Invalid request. Please select a valid PC inventory entry to edit.";
        }
        ?>

        <div class="back-link">
            <a href="index.php">Back to PC Inventory Report</a>
        </div>
    </div>
</body>
</html>
