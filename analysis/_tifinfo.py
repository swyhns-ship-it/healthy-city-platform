# -*- coding: utf-8 -*-
import os, numpy as np
from osgeo import gdal
for f in [r"C:\Users\Administrator\Downloads\SH_greenfrac_100m.tif",
          r"C:\Users\Administrator\Downloads\SH_green_100m.tif"]:
    ds = gdal.Open(f); b = ds.GetRasterBand(1); a = b.ReadAsArray()
    print(os.path.basename(f))
    print("  size", ds.RasterXSize, ds.RasterYSize, "bands", ds.RasterCount)
    print("  geotransform", [round(x, 3) for x in ds.GetGeoTransform()])
    print("  proj", ds.GetProjection()[:90])
    print("  dtype", a.dtype, "min", float(np.nanmin(a)), "max", float(np.nanmax(a)),
          "nodata", b.GetNoDataValue())
