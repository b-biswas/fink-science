# Copyright 2020 AstroLab Software
# Author: Julien Peloton
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from pyspark.sql.functions import pandas_udf, PandasUDFType
from pyspark.sql.types import IntegerType

from fink_science import __file__
import os

import pandas as pd
import numpy as np

from fink_science.tester import spark_unit_tests

@pandas_udf(IntegerType(), PandasUDFType.SCALAR)
def roid_catcher(jd, ndethist, sgscore1, ssdistnr, distpsnr1):
    """ Determine if the alert is an asteroid using two methods:
        1. The alert has been flagged as an asteroid by ZTF (MPC) within 5"
        2. The alert satisfies Fink criteria for an asteroid
            2.1 No stellar counterpart, sgscore1 < 0.76 (Tachibana & Miller 2018)
            2.2 Number of detection is 1 or 2
            2.3 No Panstarrs counterpart within 1"
            2.4 If 2 detections, observations must be done within 30 min.

    The alerts are labeled using:
        [3] if the asteroid has been flagged by ZTF
        [2] if the asteroid has been flagged by Fink
        [1] if is the first time ZTF sees this object
        [0] if it is likely not an asteroid

    Parameters
    ----------
    fid: Spark DataFrame Column
        Filter IDs (ints)
    magpsf: Spark DataFrame Column
        Magnitude from PSF-fit photometry (floats)
    ssdistnr: Spark DataFrame Column
        Distance to nearest known solar system object,
        set to -999.0 if none [arcsec].

    Returns
    ----------
    out: integer
        3 if the asteroid has been flagged by ZTF
        2 if the asteroid has been flagged by Fink
        1 if it is the first time ZTF sees this object
        0 if it is likely not an asteroid

    Examples
    ----------
    >>> from fink_science.utilities import concat_col
    >>> from pyspark.sql import functions as F

    >>> df = spark.read.load(ztf_alert_sample)

    # Required alert columns
    >>> what = ['jd']

    # Use for creating temp name
    >>> prefix = 'c'
    >>> what_prefix = [prefix + i for i in what]

    # Append temp columns with historical + current measurements
    >>> for colname in what:
    ...    df = concat_col(df, colname, prefix=prefix)

    # Perform the fit + classification (default model)
    >>> args = ['cjd', 'candidate.ndethist', 'candidate.sgscore1', 'candidate.ssdistnr', 'candidate.distpsnr1']
    >>> df = df.withColumn('roid', roid_catcher(*args))

    # Drop temp columns
    >>> df = df.drop(*what_prefix)

    >>> df.agg({"roid": "min"}).collect()[0][0]
    0
    """
    flags = np.zeros_like(ndethist.values, dtype=int)

    # first detection
    f0 = ndethist == 1
    flags[f0] = 1

    # Probable asteroid
    f1 = sgscore1 < 0.76
    f2 = ndethist <= 2
    flags[f1 & f2] = 2

    # criterion on distance to Panstarr (1 arcsec)
    f_distance1 = distpsnr1 < 1
    f_distance2 = distpsnr1 > 0
    mask_roid = f_distance1 & f_distance2
    flags[mask_roid] = 0

    # Remove long trend
    f3 = ndethist == 2
    f4 = jd[f3].apply(lambda x: np.diff(x)[-1]) > (30. / (24. * 60.))
    flags[f3 & f4] = 0

    # Add ZTF information
    if ssdistnr is not None:
        # Caught by ZTF already
        f_distance1 = ssdistnr > 0
        f_distance2 = ssdistnr < 5
        mask_roid = f_distance1 & f_distance2
        flags[mask_roid] = 3

    return pd.Series(flags)


if __name__ == "__main__":
    """ Execute the test suite """

    globs = globals()
    path = os.path.dirname(__file__)
    ztf_alert_sample = 'file://{}/data/alerts/alerts.parquet'.format(path)
    globs["ztf_alert_sample"] = ztf_alert_sample

    # Run the test suite
    spark_unit_tests(globs)
