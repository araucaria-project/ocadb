#!/usr/bin/env python
import sys
import random
import datetime

if __name__ == '__main__':
    # sys.argv[1] - number of observations curl insert commands to generate
    # sys.argv[2] - a valid api JWT token
    #
    # to insert through api use
    # generate_observations_curl_inserts.py N jwt | bash

    N = int(sys.argv[1])
    ts = int(datetime.datetime.now().timestamp())
    jwt = sys.argv[2]

    metadata = '''{ "quality_checks": { "fwhm": { "id": "fwhm","quality_value": 0,"comment": "GOOD: FWHM is on good level.","data_source": "raw_fits","metadata": { "measured_fwhm": 3.332855176283106,"fwhm_x": 3.332855176283106,"fwhm_y": 3.3239884212137207,"fwhm_levels": { "good": { "min": 0,"max": 3.5},"warn": { "min": 3.5,"max": 4.5},"bad": { "min": 4.5}}}},"stars_presence": { "id": "stars_presence","quality_value": 0,"comment": "GOOD: stars quality ok.","data_source": "raw_fits","metadata": { "status": "ok","sum_by_class": { "0": 4136363,"1": 52008,"2": 3604,"3": 2142,"4": 187},"ratio_by_class": { "0": 0.986186,"1": 0.0124,"2": 0.000859,"3": 0.000511,"4": 4.5e-05},"ratio_no_bkg": { "1": 0.897603,"2": 0.062201,"3": 0.036969,"4": 0.003227},"good_ratio_no_bkg_thresh": 0.4,"bad_ratio_no_bkg_thresh": 0.05}},"final": { "id": "final","quality_value": 0,"comment": "GOOD: Quality checks success, check zb08c_0898_65386.json for details."}},"objects": { "ngc6604_check1": { "quality_checks": { "saturation": { "id": "saturation","quality_value": 0,"comment": "GOOD: Object saturation is on good level.","data_source": "raw_fits","metadata": { "measured_saturation": 41114.0,"max_saturation": 49151.25,"min_saturation": 655.35}},"not_in_frame": { "id": "not_in_frame","quality_value": 0,"comment": "GOOD: Object is in the frame.","data_source": "raw_fits","metadata": { "x_pix_loc": 539.1134467044594,"y_pix_loc": 1619.1435804860564}},"too_close_to_frame_edge": { "id": "too_close_to_frame_edge","quality_value": 0,"comment": "GOOD: The object is not too close to the edge of the frame.","data_source": "raw_fits","metadata": { "x_edge_dist": 539.1134467044594,"y_edge_dist": 428.8564195139436,"edge_distance_restrict_pix": 50}},"final": { "id": "final","quality_value": 0,"comment": "GOOD: Quality checks success, check zb08c_0898_65386.json for details."}}},"ngc6604_check2": { "quality_checks": { "saturation": { "id": "saturation","quality_value": 2,"comment": "BAD: Object saturation is on bad level.","data_source": "raw_fits","metadata": { "measured_saturation": 64057.0,"max_saturation": 49151.25,"min_saturation": 655.35}},"not_in_frame": { "id": "not_in_frame","quality_value": 0,"comment": "GOOD: Object is in the frame.","data_source": "raw_fits","metadata": { "x_pix_loc": 1187.7338634971384,"y_pix_loc": 856.1368468753377}},"too_close_to_frame_edge": { "id": "too_close_to_frame_edge","quality_value": 0,"comment": "GOOD: The object is not too close to the edge of the frame.","data_source": "raw_fits","metadata": { "x_edge_dist": 860.2661365028616,"y_edge_dist": 856.1368468753377,"edge_distance_restrict_pix": 50}},"final": { "id": "final","quality_value": 2,"comment": "BAD: Some quality checks failed, check zb08c_0898_65386.json for details."}}},"ngc6604_check3": { "quality_checks": { "saturation": { "id": "saturation","quality_value": 2,"comment": "BAD: Object saturation is on bad level.","data_source": "raw_fits","metadata": { "measured_saturation": 0,"max_saturation": 49151.25,"min_saturation": 655.35}},"final": { "id": "final","quality_value": 2,"comment": "BAD: Some quality checks failed, check zb08c_0898_65386.json for details."}}}}}'''

    for x in range(N):
        rnd_ra = str(random.uniform(0.0, 360.0))
        rnd_dec = str(random.uniform(-90.0, 90.0))

        db_curl_insert = '''curl -X POST 'http://localhost:8084/api/v1/observations/' \\
  --header 'Content-Type: application/json' \\
  --header 'Authorization: Bearer ''' + jwt + '''\' \\
  --data '{"filename": "''' + str(ts) + '''_''' + str(x) + '''.fits","fits_header": {"SIMPLE": "T", "BITPIX": "16", "NAXIS": "2", "NAXIS1": "2048", "NAXIS2": "2048", "OCASTD": "1.0.2   ", "OBSERVAT": "OCA     ", "OBS-LAT": "-24.59806", "OBS-LONG": "-70.19638", "OBS-ELEV": "2817", "ORIGIN": "CAMK PAN", "TELESCOP": "zb08    ", "DATE-OBS": "2025-08-11T03:41:33.428132", "JD": "2460898.6538591217", "RA": "''' + rnd_ra + '''", "DEC": "''' + rnd_dec + '''", "EQUINOX": "2000    ", "RA_OBJ": "", "DEC_OBJ": "", "RA_TEL": "''' + rnd_ra + '''", "DEC_TEL": "''' + rnd_dec + '''", "ALT_TEL": "58.57311553811331", "AZ_TEL": "287.59019217185767", "AIRMASS": "1.1715108297046006", "OBSMODE": "", "FOCUS": "15399", "ROTATOR": "150.84388732910156", "OBSERVER": "", "IMAGETYP": "science ", "OBSTYPE": "science ", "OBJECT": "NGC6604 ", "OBS-PROG": "", "NLOOPS": "2", "LOOP": "1", "FILTER": "g       ", "EXPTIME": "90.0", "INSTRUME": "DW936_BV", "CCD-TEMP": "-59.12799835205078", "SET-TEMP": "", "XBINNING": "1", "YBINNING": "1", "READ-MOD": "2", "GAIN-MOD": "2", "GAIN": "0.97", "RON": "10.4", "SUBRASTR": "", "SCALE": "0.504", "SATURATE": "", "PIERSIDE": "", "FLAT_ERA": "1", "ZERO_ERA": "0", "DARK_ERA": "0", "TEST": "0", "CCD-BLCL": "", "CCD-SCMP": "", "CCD-PORT": "", "CCD-VSSP": "", "BZERO": "32768"}, "metadata": ''' + metadata + '''}' '''

        print(db_curl_insert)
        print()
