# overall

all float metrics are > 0

there are 19 AS with a non zero metric value.

mnrs=# select asn from results where m1 != 0 or m1c != 0 or m2c != 0 or m3 != 0 group by asn order by asn;
  asn
-------
   174
   286
  2603
  2914
  3267
  3303
  3356
  3549
  4323
  5511
  6461
  7015
  7575
  7922
 16735
 20115
 33660
 37100
 42861
(19 rows)


# m1

there are only 2 ASN's with a non zero m1 value


mnrs=# select asn, report_id, m1 from results where m1 != 0;                                                                             
  asn  | report_id | m1                                                                                                                  
-------+-----------+-----                                                                                                                
 20115 |        16 | 0.5                                                                                                                 
 16735 |        16 |   4                                                                                                                 
(2 rows)                                                                                                                                 
                          

# m1c


mnrs=# select asn, report_id, m1c from results where m1c != 0 order by asn,report_id;
  asn  | report_id | m1c  
-------+-----------+------
   174 |        16 |   26
   174 |        17 | 24.5
   174 |        18 |   30
   174 |        19 | 23.5
  2914 |        16 |   13
  2914 |        17 |   10
  2914 |        18 |   19
  2914 |        19 |   11
  3356 |        16 | 30.5
  3356 |        17 |   30
  3356 |        18 |   29
  3356 |        19 |   24
  3549 |        16 |   13
  3549 |        17 |    1
  3549 |        18 |   10
  3549 |        19 |   10
  4323 |        16 |    8
  4323 |        18 |  0.5
  5511 |        16 |   27
  5511 |        17 | 28.5
  5511 |        18 |   19
  5511 |        19 |   32
  6461 |        16 |   31
  6461 |        17 |   31
  6461 |        18 |   28
  6461 |        19 |   25
  7015 |        17 |   10
  7922 |        16 |  2.5
  7922 |        17 |    4
 42861 |        18 |    1
(30 rows)


# m2

mnrs=# select asn, report_id, m2 from results where m2 != 0 order by asn,report_id;
  asn  | report_id |  m2  
-------+-----------+------
   174 |        19 |   10
   286 |        16 |  0.5
  3292 |        18 |    3
  3292 |        19 |   11
  3356 |        16 |    6
  3356 |        17 |   22
  3356 |        18 |   15
  3356 |        19 |  3.5
  3549 |        16 |  0.5
  3549 |        17 |   13
  3549 |        18 |   27
  3549 |        19 | 15.5
  5607 |        17 |  0.5
  6461 |        18 |  0.5
 28000 |        17 |    2
 28000 |        18 |   13
(16 rows)

# m2c

mnrs=# select asn, report_id, m2c from results where m2c != 0 order by asn,report_id;
  asn  | report_id | m2c 
-------+-----------+-----
   174 |        16 |   6
   174 |        17 |  30
   174 |        18 |  31
   174 |        19 |  32
   286 |        17 | 0.5
  2603 |        17 |   3
  2603 |        18 |   9
  2914 |        16 | 1.5
  2914 |        17 |  14
  2914 |        18 | 0.5
  2914 |        19 |  26
  3267 |        18 | 0.5
  3303 |        19 |  15
  3356 |        16 |   4
  3356 |        17 |  20
  3356 |        18 |  17
  3356 |        19 |  18
  3549 |        18 |  30
  3549 |        19 |  21
  5511 |        17 |  15
  5511 |        19 |   2
  6461 |        17 |  14
  6461 |        18 |  14
  6461 |        19 |   1
  7575 |        17 |  13
  7575 |        18 |   1
 16735 |        18 |  18
 20115 |        18 |   1
 33660 |        19 |   8
 37100 |        18 |   3
(30 rows)


# m3 

only 7 non-zero values

mnrs=# select asn, report_id, m3 from results where m3 != 0 order by asn,report_id;
 asn  | report_id | m3 
------+-----------+----
  174 |        16 |  2
  174 |        17 | 31
  174 |        18 |  7
 3549 |        16 |  7
 3549 |        17 | 31
 3549 |        18 | 20
 3549 |        19 | 32
(7 rows)


# m8

most of the m8 data is true (12 out of 742 are false)

mnrs=# select count(m8) from results where m8=false;
 count 
-------
    12
(1 row)



# m7irr

mnrs=# select count(asn) from results where m7irr != 1;
 count 
-------
   373
(1 row)


