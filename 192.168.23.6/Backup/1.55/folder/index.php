<!DOCTYPE html>
<html>
<head>
    <title>Form Input Data PC Inventory</title>
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
        }
        .form-container {
            background: #fff;
            border: 1px solid #ccc;
            border-radius: 5px;
            padding: 20px;
            box-shadow: 0px 0px 10px #aaa;
        }
        label {
            display: block;
            margin-bottom: 10px;
        }
        input[type="text"], select, input[type="number"] {
            width: 100%;
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #ccc;
            border-radius: 4px;
            box-sizing: border-box;
        }
        input[type="radio"] {
            margin-right: 10px;
        }
        select {
            width: 100%;
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #ccc;
            border-radius: 4px;
            box-sizing: border-box;
        }
        input[type="submit"] {
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 10px 20px;
            cursor: pointer;
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
    <div class="form-container">
	<div class="menu">
	<a href="report.php">Report</a>
	</div>

        <h2>Form Input Data PC Inventory</h2>
        <form method="post" action="insert_data.php">
            <label for="device">Device:</label>
            <select name="device" >
                <option value="PC">PC</option>
                <option value="Laptop">Laptop</option>
                <option value="Server">Server</option>
                <option value="Monitor">Monitor</option>
                <option value="UPS">UPS</option>
		<option value="Printer">Printer</option>
		<option value="Scanner">Scanner</option>
		<option value="Encoder">Encoder</option>
		<option value="Micros UWS">Micros UWS</option>
		<option value="Micros Printer">Micros Printer</option>

            </select>

            <label for="device_brand">Device Brand:</label>
            <input type="text" name="device_brand" >

       	    <label for="device_brand">Device SN:</label>
            <input type="text" name="device_sn" >


            <label for="processor">Processor:</label>
            <input type="text" name="processor" >

            <label for="hardisk">Hardisk:</label>
            <input type="text" name="hardisk" >

            <label for="ram">RAM:</label>
            <input type="text" name="ram" >

            <label for="windows_version">Windows Version:</label>
            <select name="windows_version" >
                <option value="-">-</option>
                <option value="Windows 7">Windows 7</option>
                <option value="Windows 10">Windows 10</option>
                <option value="Windows 11">Windows 11</option>
                <option value="Windows Server 2008">Windows Server 2008</option>
                <option value="Windows Server 2012">Windows Server 2012</option>
                <option value="Windows Server 2016">Windows Server 2016</option>
				<option value="Windows Server 2019">Windows Server 2019</option>
				<option value="Linux">Linux</option>
				
            </select>
	    <label for="Windows_SN">Windows_SN:</label>
            <input type="text" name="windows_sn" >

            <label for="office_version">Office Version:</label>
            <select name="office_version" >
 		<option value="-">-</option>
		        <option value="Office 2010 Starter">Office 2010 Starter</option>
                <option value="Office 2010">Office 2010</option>
                <option value="Office 2013">Office 2013</option>
                <option value="Office 2016">Office 2016</option>
                <option value="Office 2019">Office 2019</option>
                <option value="Office 2021">Office 2021</option>
            </select>
 	    <label for="Office_SN">Office_SN:</label>
            <input type="text" name="office_sn" >

            <label for="antivirus">Antivirus:</label>
	    <input type="text" name="antivirus" >
            

            <label for="ip_address">IP Address:</label>
            <input type="text" name="ip_address" >

            <label for="pcname">Computer Name:</label>
            <input type="text" name="pcname" >


			<label for="dept">Department:</label>
			<select name="dept">
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

            <label for="staff">User:</label>
            <input type="text" name="staff" >


            <label for="vendor">Vendor:</label>
            <input type="text" name="vendor" >

            <label for="purchase_year">Purchase Year:</label>
            <input type="number" name="purchase_year" >
  	        <label for="status">Status:</label>
            <input type="radio" name="status" value="Active" checked > Active
            <input type="radio" name="status" value="Not Active" > Not Active
            <br/><br/>
            <input type="submit" value="Simpan">

        </form>
    </div>
</body>
</html>
