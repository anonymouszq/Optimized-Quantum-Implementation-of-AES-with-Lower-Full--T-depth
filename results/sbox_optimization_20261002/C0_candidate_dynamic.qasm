OPENQASM 2.0;
include "qelib1.inc";
qreg q[72];
creg m0[1];
creg m1[1];
creg m2[1];
creg m3[1];
creg m4[1];
creg m5[1];
creg m6[1];
creg m7[1];
creg m8[1];
creg m9[1];
creg m10[1];
creg m11[1];
creg m12[1];
creg m13[1];
creg m14[1];
creg m15[1];
creg m16[1];
creg m17[1];
creg m18[1];
creg m19[1];
creg m20[1];
creg m21[1];
creg m22[1];
creg m23[1];
creg m24[1];
creg m25[1];
creg m26[1];
creg m27[1];
creg m28[1];
creg m29[1];
creg m30[1];
creg m31[1];
creg m32[1];
creg m33[1];

// Layer 1
cx q[6],q[4];
cx q[3],q[40];
cx q[2],q[1];
cx q[5],q[38];
cx q[0],q[37];
h q[53];
h q[57];
h q[59];
h q[61];
cx q[7],q[50];
h q[54];
h q[47];
h q[27];
h q[18];
h q[51];
h q[56];
h q[17];
h q[49];
h q[22];
h q[30];
h q[32];
h q[31];
h q[26];
h q[35];
h q[36];
h q[16];
h q[25];
h q[34];
h q[19];
h q[21];
h q[20];
h q[24];
h q[33];
h q[23];
h q[28];
h q[8];
h q[9];
h q[29];
h q[10];
h q[11];

// Layer 2
cx q[4],q[2];
cx q[0],q[3];
cx q[1],q[41];
cx q[5],q[40];
cx q[6],q[37];
cx q[61],q[44];
cx q[57],q[45];
cx q[54],q[42];
cx q[56],q[39];
cx q[18],q[13];
cx q[27],q[71];
cx q[30],q[65];
cx q[26],q[68];
cx q[17],q[69];
cx q[25],q[70];
cx q[33],q[14];
cx q[23],q[66];

// Layer 3
cx q[3],q[4];
cx q[5],q[2];
cx q[1],q[39];
cx q[0],q[38];
cx q[59],q[41];
cx q[37],q[58];
cx q[40],q[62];

// Layer 4
cx q[4],q[41];
cx q[7],q[1];
cx q[6],q[5];
cx q[3],q[46];
cx q[2],q[44];
cx q[57],q[37];
cx q[38],q[60];
cx q[61],q[40];

// Layer 5
cx q[4],q[44];
cx q[1],q[0];
cx q[2],q[45];
cx q[3],q[42];
cx q[46],q[15];
cx q[41],q[60];
cx q[51],q[6];
cx q[59],q[38];

// Layer 6
cx q[4],q[43];
cx q[2],q[39];
cx q[1],q[6];
cx q[0],q[3];
cx q[5],q[42];
cx q[44],q[62];
cx q[45],q[58];
cx q[56],q[46];

// Layer 7
cx q[53],q[2];
cx q[7],q[4];
cx q[1],q[52];
cx q[43],q[55];
cx q[0],q[5];
cx q[49],q[3];
cx q[39],q[15];

// Layer 8
cx q[1],q[2];
cx q[0],q[12];
cx q[4],q[48];
cx q[6],q[52];
cx q[47],q[5];
cx q[3],q[50];
cx q[54],q[43];
cx q[42],q[55];
cx q[49],q[7];

// Layer 9
cx q[53],q[0];
cx q[47],q[4];
cx q[51],q[1];
cx q[2],q[12];
cx q[5],q[48];

// Layer 10
t q[16];
t q[17];
t q[18];
t q[19];
t q[20];
t q[21];
t q[22];
t q[23];
t q[24];
t q[25];
t q[26];
t q[27];
t q[28];
t q[29];
t q[30];
t q[31];
t q[32];
t q[33];
t q[34];
t q[35];
t q[36];
t q[8];
t q[9];
t q[10];
t q[11];
tdg q[5];
tdg q[4];
t q[47];
t q[48];
tdg q[3];
tdg q[7];
t q[49];
t q[50];
tdg q[6];
tdg q[1];
t q[51];
t q[52];
tdg q[2];
tdg q[0];
t q[53];
t q[12];
tdg q[42];
tdg q[43];
t q[54];
t q[55];
tdg q[39];
tdg q[46];
t q[56];
t q[15];
tdg q[45];
tdg q[37];
t q[57];
t q[58];
tdg q[41];
tdg q[38];
t q[59];
t q[60];
tdg q[44];
tdg q[40];
t q[61];
t q[62];

// Layer 11
cx q[41],q[60];
cx q[6],q[52];
cx q[53],q[0];
cx q[59],q[38];
cx q[61],q[40];
cx q[39],q[15];
cx q[57],q[37];
cx q[2],q[12];
cx q[44],q[62];
cx q[42],q[55];
cx q[51],q[1];
cx q[3],q[50];
cx q[54],q[43];
cx q[5],q[48];
cx q[47],q[4];
cx q[49],q[7];
cx q[45],q[58];
cx q[56],q[46];

// Layer 12
cx q[59],q[41];
cx q[53],q[2];
cx q[61],q[44];
cx q[57],q[45];
cx q[51],q[6];
cx q[54],q[42];
cx q[7],q[50];
cx q[56],q[39];
cx q[47],q[5];
cx q[43],q[55];
cx q[40],q[60];
cx q[1],q[52];
cx q[49],q[3];
cx q[4],q[48];
cx q[37],q[58];
cx q[0],q[12];
cx q[46],q[15];
cx q[38],q[26];

// Layer 13
h q[53];
h q[59];
h q[57];
h q[61];
cx q[41],q[7];
cx q[1],q[15];
cx q[38],q[55];
h q[54];
h q[51];
h q[56];
h q[47];
cx q[44],q[43];
cx q[3],q[39];
cx q[2],q[52];
h q[49];
cx q[45],q[12];
cx q[40],q[27];
cx q[32],q[48];
cx q[37],q[25];
cx q[21],q[42];

// Layer 14
cx q[38],q[60];
s q[59];
s q[53];
cx q[7],q[48];
s q[61];
s q[57];
s q[54];
s q[51];
cx q[45],q[43];
cx q[41],q[58];
s q[47];
cx q[46],q[3];
cx q[2],q[4];
cx q[15],q[62];
cx q[44],q[36];
cx q[37],q[42];
s q[49];
s q[56];

// Layer 15
cx q[57],q[53];
cx q[56],q[59];
cx q[55],q[54];
cx q[37],q[51];
cx q[7],q[58];
cx q[60],q[47];
cx q[5],q[43];
cx q[41],q[4];
cx q[15],q[50];
cx q[40],q[62];
cx q[2],q[31];
cx q[28],q[3];

// Layer 16
cx q[0],q[53];
cx q[56],q[61];
cx q[51],q[57];
cx q[41],q[54];
cx q[44],q[47];
cx q[58],q[52];
cx q[43],q[5];
cx q[37],q[60];
cx q[40],q[55];
cx q[15],q[48];
cx q[50],q[30];

// Layer 17
cx q[59],q[53];
cx q[61],q[57];
cx q[37],q[0];
cx q[52],q[39];
cx q[44],q[7];
cx q[41],q[62];
cx q[55],q[46];
cx q[50],q[15];
cx q[19],q[43];
cx q[60],q[23];
cx q[29],q[58];
cx q[40],q[42];

// Layer 18
cx q[53],q[1];
cx q[57],q[4];
cx q[54],q[59];
cx q[47],q[61];
cx q[0],q[6];
cx q[55],q[24];
cx q[37],q[3];
cx q[52],q[33];
cx q[39],q[20];
cx q[62],q[28];

// Layer 19
cx q[53],q[7];
cx q[57],q[1];
cx q[49],q[59];
cx q[54],q[61];
cx q[0],q[3];
cx q[20],q[64];
cx q[37],q[51];
cx q[40],q[47];

// Layer 20
cx q[59],q[53];
cx q[57],q[12];
cx q[61],q[5];
cx q[1],q[15];
cx q[41],q[54];
cx q[0],q[42];
cx q[7],q[46];
cx q[44],q[47];

// Layer 21
cx q[2],q[53];
cx q[61],q[57];
cx q[59],q[63];
cx q[5],q[6];
cx q[35],q[41];
cx q[1],q[18];
cx q[37],q[0];
cx q[7],q[17];
cx q[15],q[32];
cx q[46],q[64];
cx q[12],q[19];
cx q[38],q[54];

// Layer 22
cx q[45],q[57];
cx q[53],q[67];
cx q[59],q[61];
cx q[63],q[22];
cx q[6],q[65];
cx q[16],q[5];
cx q[12],q[3];
cx q[15],q[66];
cx q[46],q[29];
cx q[64],q[39];

// Layer 23
cx q[57],q[53];
cx q[67],q[14];
cx q[22],q[0];
cx q[34],q[45];
cx q[59],q[69];
cx q[61],q[13];
cx q[6],q[21];
cx q[4],q[16];
cx q[66],q[60];
cx q[48],q[15];
cx q[43],q[12];
cx q[3],q[62];
cx q[65],q[50];
cx q[58],q[46];

// Layer 24
cx q[53],q[71];
cx q[57],q[35];
cx q[31],q[59];
cx q[61],q[70];
cx q[13],q[1];
cx q[0],q[63];
cx q[5],q[4];
cx q[24],q[67];
cx q[14],q[52];
cx q[42],q[6];
cx q[69],q[7];

// Layer 25
cx q[36],q[53];
cx q[57],q[68];
cx q[61],q[34];
cx q[59],q[2];
cx q[70],q[37];
cx q[67],q[55];
cx q[71],q[40];

// Layer 26
cx q[53],q[44];
cx q[41],q[57];
cx q[45],q[61];
cx q[68],q[38];

// Layer 27
tdg q[5];
t q[4];
tdg q[16];
tdg q[69];
t q[7];
tdg q[17];
tdg q[13];
t q[1];
tdg q[18];
tdg q[43];
t q[12];
tdg q[19];
tdg q[39];
t q[64];
tdg q[20];
tdg q[42];
t q[6];
tdg q[21];
tdg q[63];
t q[0];
tdg q[22];
tdg q[66];
t q[60];
tdg q[23];
tdg q[55];
t q[67];
tdg q[24];
tdg q[70];
t q[37];
tdg q[25];
tdg q[68];
t q[38];
tdg q[26];
tdg q[71];
t q[40];
tdg q[27];
tdg q[3];
t q[62];
tdg q[28];
tdg q[58];
t q[46];
tdg q[29];
tdg q[65];
t q[50];
tdg q[30];
tdg q[2];
t q[59];
tdg q[31];
tdg q[48];
t q[15];
tdg q[32];
tdg q[14];
t q[52];
tdg q[33];
tdg q[45];
t q[61];
tdg q[34];
tdg q[41];
t q[57];
tdg q[35];
tdg q[44];
t q[53];
tdg q[36];

// Layer 28
cx q[70],q[37];
cx q[45],q[61];
cx q[59],q[2];
cx q[13],q[1];
cx q[0],q[63];
cx q[67],q[55];
cx q[14],q[52];
cx q[53],q[44];
cx q[41],q[57];
cx q[68],q[38];
cx q[66],q[60];
cx q[65],q[50];
cx q[5],q[4];
cx q[71],q[40];
cx q[69],q[7];
cx q[64],q[39];
cx q[3],q[62];
cx q[48],q[15];
cx q[58],q[46];
cx q[43],q[12];
cx q[42],q[6];

// Layer 29
cx q[22],q[0];
cx q[37],q[25];
cx q[61],q[34];
cx q[1],q[18];
cx q[31],q[59];
cx q[52],q[33];
cx q[36],q[53];
cx q[57],q[35];
cx q[50],q[30];
cx q[24],q[67];
cx q[38],q[26];
cx q[40],q[27];
cx q[60],q[23];
cx q[7],q[17];
cx q[4],q[16];
cx q[20],q[64];
cx q[63],q[65];
cx q[6],q[21];
cx q[46],q[29];
cx q[62],q[28];
cx q[15],q[32];
cx q[12],q[19];
cx q[44],q[48];
cx q[2],q[45];

// Layer 30
cx q[34],q[45];
cx q[18],q[13];
cx q[25],q[70];
cx q[55],q[24];
cx q[63],q[22];
cx q[2],q[31];
cx q[53],q[57];
cx q[30],q[65];
cx q[35],q[41];
cx q[33],q[14];
cx q[26],q[68];
cx q[44],q[36];
cx q[40],q[38];
cx q[27],q[71];
cx q[23],q[66];
cx q[17],q[69];
cx q[16],q[5];
cx q[39],q[20];
cx q[12],q[4];
cx q[29],q[58];
cx q[19],q[43];
cx q[7],q[3];
cx q[32],q[48];
cx q[21],q[42];
cx q[11],q[60];
cx q[9],q[52];

// Layer 31
cx q[61],q[70];
h q[18];
h q[25];
h q[34];
h q[22];
h q[31];
cx q[66],q[3];
h q[30];
h q[24];
h q[33];
h q[26];
h q[35];
cx q[37],q[40];
h q[27];
h q[36];
cx q[44],q[52];
h q[17];
cx q[57],q[14];
h q[16];
cx q[69],q[46];
cx q[1],q[12];
h q[20];
cx q[64],q[63];
cx q[2],q[48];
h q[29];
h q[19];
h q[21];
h q[32];
h q[4];
h q[23];
cx q[45],q[50];
cx q[38],q[55];
cx q[5],q[6];

// Layer 32
cx q[18],q[53];
s q[25];
s q[34];
s q[22];
s q[31];
cx q[27],q[70];
cx q[0],q[37];
cx q[15],q[66];
s q[30];
cx q[17],q[63];
cx q[16],q[46];
cx q[41],q[52];
cx q[40],q[60];
cx q[28],q[3];
s q[26];
cx q[36],q[62];
cx q[57],q[67];
cx q[64],q[7];
cx q[2],q[44];
s q[35];
cx q[45],q[48];
h q[14];
cx q[69],q[59];
s q[19];
s q[20];
s q[21];
s q[33];
s q[24];
s q[32];
s q[23];
s q[29];

// Layer 33
cx q[18],q[61];
cx q[26],q[22];
cx q[35],q[31];
cx q[33],q[34];
cx q[24],q[25];
cx q[36],q[30];
cx q[27],q[67];
cx q[53],q[46];
cx q[17],q[55];
cx q[41],q[44];
cx q[39],q[0];
cx q[64],q[12];
cx q[21],q[70];
cx q[32],q[62];
h q[28];
h q[7];
cx q[43],q[40];
cx q[14],q[58];
cx q[42],q[37];
s q[16];

// Layer 34
cx q[18],q[68];
cx q[34],q[50];
cx q[25],q[70];
cx q[20],q[26];
cx q[53],q[55];
cx q[38],q[0];
s q[27];
cx q[46],q[66];
cx q[29],q[35];
cx q[45],q[41];
s q[17];
s q[36];
cx q[44],q[58];
cx q[4],q[67];
cx q[33],q[62];
h q[12];
cx q[39],q[40];
s q[28];

// Layer 35
cx q[18],q[71];
cx q[22],q[25];
cx q[31],q[34];
cx q[53],q[17];
cx q[30],q[50];
cx q[68],q[63];
cx q[66],q[3];
cx q[41],q[62];
cx q[70],q[40];
h q[0];
cx q[19],q[67];

// Layer 36
s q[18];
cx q[27],q[22];
cx q[30],q[31];
cx q[53],q[71];
cx q[46],q[17];
cx q[63],q[48];
cx q[10],q[68];
cx q[0],q[55];
cx q[7],q[66];
cx q[24],q[67];
cx q[28],q[62];
cx q[12],q[34];

// Layer 37
cx q[61],q[18];
cx q[26],q[27];
cx q[36],q[30];
cx q[17],q[60];
cx q[21],q[22];
cx q[63],q[6];
cx q[8],q[31];
cx q[16],q[68];
cx q[46],q[71];
cx q[55],q[40];
cx q[25],q[10];
cx q[23],q[67];
cx q[66],q[37];
cx q[0],q[70];

// Layer 38
cx q[53],q[61];
cx q[18],q[65];
cx q[19],q[27];
cx q[22],q[59];
cx q[35],q[36];
cx q[17],q[3];
cx q[23],q[26];
cx q[67],q[6];
cx q[4],q[63];
cx q[68],q[25];

// Layer 39
cx q[61],q[15];
cx q[57],q[53];
cx q[13],q[18];
cx q[17],q[52];
cx q[27],q[9];
cx q[28],q[36];
cx q[24],q[26];
cx q[32],q[35];
h q[65];
cx q[14],q[22];

// Layer 40
cx q[1],q[61];
cx q[16],q[53];
cx q[3],q[18];
cx q[48],q[13];
cx q[26],q[37];
cx q[65],q[62];
cx q[52],q[27];
cx q[17],q[8];
cx q[36],q[11];
h q[15];
cx q[34],q[57];
cx q[33],q[35];

// Layer 41
cx q[53],q[57];
cx q[62],q[18];
h q[61];
cx q[17],q[58];
cx q[15],q[35];
cx q[60],q[36];
cx q[5],q[13];
cx q[65],q[3];
cx q[7],q[26];

// Layer 42
cx q[61],q[50];
cx q[58],q[59];
cx q[64],q[57];
cx q[12],q[53];
cx q[31],q[17];
cx q[69],q[13];
cx q[35],q[71];
cx q[15],q[46];

// Layer 43
cx q[50],q[13];
cx q[69],q[57];
cx q[61],q[48];

// Layer 44
tdg q[67];
tdg q[63];
t q[4];
t q[6];
tdg q[66];
tdg q[26];
t q[7];
t q[37];
tdg q[52];
t q[27];
tdg q[9];
tdg q[55];
tdg q[70];
t q[0];
t q[40];
tdg q[68];
t q[25];
tdg q[10];
tdg q[58];
tdg q[22];
t q[14];
t q[59];
tdg q[62];
tdg q[3];
t q[65];
t q[18];
tdg q[35];
tdg q[46];
t q[15];
t q[71];
tdg q[60];
t q[36];
tdg q[11];
tdg q[50];
tdg q[48];
t q[61];
t q[13];
tdg q[34];
tdg q[53];
t q[12];
t q[57];
tdg q[31];
t q[17];
tdg q[8];

// Layer 45
cx q[52],q[27];
cx q[66],q[37];
cx q[67],q[6];
cx q[60],q[36];
cx q[35],q[71];
cx q[68],q[25];
cx q[7],q[26];
cx q[31],q[17];
cx q[4],q[63];
cx q[62],q[18];
cx q[58],q[59];
cx q[34],q[57];
cx q[15],q[46];
cx q[55],q[40];
cx q[50],q[13];
cx q[12],q[53];
cx q[65],q[3];
cx q[14],q[22];
cx q[61],q[48];
cx q[0],q[70];

// Layer 46
cx q[27],q[9];
cx q[7],q[66];
cx q[4],q[67];
cx q[36],q[11];
cx q[25],q[10];
cx q[15],q[35];
cx q[63],q[6];
cx q[17],q[8];
cx q[65],q[62];
cx q[14],q[58];
cx q[12],q[34];
cx q[0],q[55];
cx q[61],q[50];
cx q[3],q[18];
cx q[22],q[59];
cx q[48],q[13];
cx q[26],q[37];
cx q[70],q[40];
cx q[53],q[57];
cx q[39],q[60];
cx q[46],q[71];

// Layer 47
cx q[9],q[52];
cx q[11],q[60];
cx q[10],q[68];
h q[7];
h q[4];
cx q[8],q[31];
h q[15];
h q[63];
h q[65];
cx q[69],q[59];
h q[14];
cx q[64],q[13];
cx q[32],q[35];
cx q[43],q[6];
h q[12];
h q[0];
cx q[1],q[37];
cx q[5],q[40];
h q[61];
cx q[19],q[27];
cx q[16],q[53];
h q[3];
cx q[17],q[58];
cx q[28],q[36];
cx q[23],q[26];
h q[48];
h q[55];
cx q[42],q[18];
cx q[21],q[22];

// Layer 48
h q[9];
s q[7];
s q[4];
h q[10];
h q[11];
s q[15];
h q[8];
cx q[59],q[57];
s q[65];
cx q[33],q[35];
s q[14];
s q[12];
s q[61];
s q[0];
cx q[40],q[58];
cx q[24],q[26];
cx q[17],q[60];
cx q[39],q[6];
h q[43];
cx q[16],q[66];
h q[5];

// Layer 49
cx q[4],q[7];
s q[9];
cx q[11],q[15];
s q[10];
cx q[61],q[12];
cx q[64],q[57];
s q[8];
cx q[35],q[36];
cx q[69],q[58];
cx q[26],q[27];
cx q[38],q[60];
cx q[17],q[52];
h q[40];
cx q[16],q[46];

// Layer 50
cx q[4],q[9];
cx q[14],q[10];
cx q[61],q[8];
s q[11];
cx q[57],q[53];
cx q[36],q[30];
cx q[58],q[71];
cx q[20],q[26];
cx q[60],q[18];
cx q[27],q[22];
h q[64];
cx q[29],q[35];
cx q[59],q[46];
h q[69];

// Layer 51
h q[4];
cx q[65],q[11];
cx q[0],q[14];
h q[61];
cx q[30],q[31];
cx q[57],q[17];
cx q[22],q[25];
h q[20];
cx q[53],q[46];
h q[60];
h q[29];
cx q[15],q[10];
cx q[8],q[7];

// Layer 52
measure q[4]->m1[0];
barrier q[4],q[67],q[63];
measure q[61]->m0[0];
barrier q[61],q[50],q[48];
h q[65];
h q[0];
measure q[20]->m6[0];
barrier q[20],q[39],q[64];
cx q[31],q[34];
cx q[26],q[22];
cx q[57],q[66];
cx q[12],q[14];
cx q[10],q[7];

// Layer 53
measure q[65]->m2[0];
barrier q[65],q[62],q[3];
measure q[0]->m3[0];
barrier q[0],q[70],q[55];
if(m1==1) cx q[67],q[63];
cx q[1],q[4];
if(m0==1) cx q[50],q[48];
cx q[53],q[61];
cx q[57],q[20];
cx q[35],q[31];
h q[26];
h q[22];
if(m6==1) cx q[39],q[64];
cx q[15],q[12];
x q[14];
x q[10];

// Layer 54
cx q[13],q[4];
cx q[19],q[67];
cx q[37],q[65];
if(m2==1) cx q[62],q[3];
if(m3==1) cx q[70],q[55];
h q[63];
h q[48];
cx q[34],q[50];
if(m0==1) x q[61];
cx q[45],q[0];
if(m6==1) x q[20];
h q[31];
h q[1];
h q[35];
h q[64];
cx q[8],q[15];

// Layer 55
cx q[53],q[37];
if(m1==1) x q[4];
h q[19];
cx q[71],q[67];
cx q[41],q[62];
cx q[21],q[70];
cx q[44],q[48];
h q[3];
h q[55];
cx q[30],q[50];
cx q[33],q[34];
cx q[2],q[0];
h q[20];
if(m2==1) x q[65];
cx q[9],q[8];
cx q[14],q[15];

// Layer 56
cx q[4],q[52];
cx q[37],q[71];
cx q[45],q[41];
cx q[27],q[70];
cx q[2],q[44];
cx q[68],q[3];
cx q[63],q[48];
cx q[38],q[55];
h q[21];
cx q[33],q[62];
cx q[36],q[30];
cx q[24],q[67];
if(m3==1) x q[0];
h q[65];
h q[34];
cx q[11],q[9];

// Layer 57
measure q[19]->m5[0];
barrier q[19],q[4],q[43];
measure q[21]->m4[0];
barrier q[21],q[42],q[40];
cx q[27],q[67];
cx q[41],q[44];
cx q[71],q[61];
cx q[53],q[63];
cx q[16],q[68];
cx q[17],q[3];
cx q[45],q[50];
cx q[25],q[70];
cx q[36],q[62];
cx q[37],q[66];
h q[33];
h q[30];
h q[48];
cx q[9],q[12];
cx q[8],q[11];

// Layer 58
cx q[6],q[19];
cx q[53],q[55];
cx q[71],q[68];
h q[27];
cx q[41],q[70];
cx q[57],q[21];
cx q[16],q[17];
cx q[44],q[0];
cx q[2],q[45];
h q[61];
cx q[59],q[63];
cx q[32],q[62];
cx q[24],q[25];
cx q[66],q[3];
cx q[23],q[67];
h q[36];
if(m4==1) cx q[42],q[40];
h q[50];
measure q[29]->m9[0];
barrier q[29],q[46],q[48];
if(m5==1) cx q[4],q[43];
x q[9];

// Layer 59
cx q[18],q[6];
cx q[71],q[53];
cx q[44],q[70];
cx q[17],q[55];
h q[68];
cx q[59],q[3];
h q[16];
h q[2];
h q[41];
cx q[28],q[62];
h q[32];
if(m4==1) x q[21];
h q[24];
if(m5==1) x q[19];
h q[66];
h q[23];
h q[45];
h q[40];
h q[25];
if(m9==1) cx q[46],q[48];
h q[43];
if(m9==1) x q[29];

// Layer 60
cx q[6],q[38];
measure q[16]->m10[0];
barrier q[16],q[52],q[5];
measure q[31]->m13[0];
barrier q[31],q[59],q[2];
measure q[33]->m19[0];
barrier q[33],q[70],q[20];
cx q[53],q[57];
cx q[17],q[63];
measure q[32]->m8[0];
barrier q[32],q[0],q[65];
cx q[71],q[37];
h q[44];
measure q[23]->m12[0];
barrier q[23],q[19],q[66];
h q[55];
h q[18];
h q[62];
h q[28];
cx q[46],q[64];
cx q[42],q[43];
h q[48];

// Layer 61
measure q[27]->m17[0];
barrier q[27],q[6],q[61];
measure q[26]->m18[0];
barrier q[26],q[38],q[68];
measure q[36]->m21[0];
barrier q[36],q[53],q[44];
measure q[35]->m22[0];
barrier q[35],q[57],q[41];
measure q[24]->m20[0];
barrier q[24],q[21],q[55];
cx q[63],q[67];
if(m19==1) cx q[70],q[20];
if(m10==1) cx q[52],q[5];
h q[17];
cx q[37],q[31];
measure q[28]->m11[0];
barrier q[28],q[3],q[62];
h q[71];
if(m13==1) cx q[59],q[2];
if(m8==1) cx q[0],q[65];
if(m12==1) cx q[19],q[66];
if(m8==1) x q[32];
if(m10==1) x q[16];
if(m12==1) x q[23];
if(m19==1) x q[33];

// Layer 62
measure q[22]->m16[0];
barrier q[22],q[63],q[60];
if(m17==1) cx q[6],q[61];
measure q[17]->m7[0];
barrier q[17],q[13],q[69];
measure q[30]->m15[0];
barrier q[30],q[67],q[50];
measure q[71]->m14[0];
barrier q[71],q[58],q[1];
if(m21==1) cx q[53],q[44];
if(m18==1) cx q[38],q[68];
measure q[34]->m23[0];
barrier q[34],q[37],q[45];
if(m22==1) cx q[57],q[41];
if(m20==1) cx q[21],q[55];
h q[20];
h q[5];
if(m13==1) x q[31];
if(m11==1) cx q[3],q[62];
h q[65];
h q[2];
h q[66];
cx q[70],q[39];
if(m17==1) x q[27];
if(m11==1) x q[28];
if(m18==1) x q[26];
if(m20==1) x q[24];
if(m21==1) x q[36];
if(m22==1) x q[35];

// Layer 63
measure q[25]->m24[0];
barrier q[25],q[31],q[18];
h q[61];
if(m7==1) cx q[13],q[69];
if(m16==1) cx q[63],q[60];
if(m14==1) cx q[58],q[1];
if(m15==1) cx q[67],q[50];
h q[68];
cx q[21],q[20];
cx q[40],q[5];
if(m23==1) cx q[37],q[45];
h q[41];
cx q[38],q[54];
cx q[4],q[3];
cx q[65],q[66];
cx q[6],q[47];
h q[44];
if(m16==1) x q[22];
h q[62];
cx q[0],q[70];
h q[55];
if(m15==1) x q[30];
if(m7==1) x q[17];
if(m14==1) x q[71];
if(m23==1) x q[34];

// Layer 64
cx q[53],q[61];
cx q[57],q[68];
cx q[40],q[67];
if(m24==1) cx q[31],q[18];
cx q[41],q[54];
h q[60];
cx q[59],q[63];
h q[69];
h q[1];
cx q[52],q[4];
cx q[38],q[43];
cx q[44],q[47];
h q[45];
cx q[13],q[46];
cx q[6],q[22];
cx q[2],q[62];
h q[50];
if(m24==1) x q[25];

// Layer 65
cx q[57],q[53];
cx q[59],q[69];
cx q[60],q[32];
cx q[31],q[58];
h q[18];
cx q[1],q[65];
cx q[44],q[43];
cx q[41],q[52];
cx q[38],q[22];
cx q[6],q[16];

// Layer 66
cx q[53],q[21];
cx q[40],q[57];
cx q[18],q[60];
cx q[37],q[31];
cx q[43],q[48];
cx q[22],q[32];
cx q[38],q[27];

// Layer 67
cx q[59],q[53];
cx q[37],q[40];
cx q[45],q[57];
cx q[60],q[27];
cx q[18],q[51];
cx q[32],q[39];
cx q[41],q[48];
cx q[38],q[55];
h q[22];

// Layer 68
cx q[59],q[40];
cx q[2],q[53];
cx q[57],q[52];
cx q[60],q[30];
cx q[47],q[37];
cx q[18],q[19];
cx q[45],q[43];
h q[32];
h q[27];

// Layer 69
cx q[54],q[59];
cx q[53],q[1];
cx q[56],q[37];
cx q[60],q[42];
cx q[52],q[70];
cx q[6],q[47];
cx q[43],q[0];
cx q[19],q[55];
cx q[18],q[16];

// Layer 70
cx q[59],q[37];
cx q[57],q[1];
cx q[53],q[13];
cx q[18],q[60];
cx q[52],q[62];
cx q[41],q[54];
cx q[44],q[47];
cx q[6],q[19];
h q[43];

// Layer 71
cx q[49],q[59];
cx q[51],q[57];
cx q[2],q[52];
cx q[1],q[50];
cx q[38],q[54];
cx q[60],q[53];
cx q[13],q[48];
h q[41];
h q[47];
h q[6];

// Layer 72
cx q[37],q[57];
cx q[59],q[53];
measure q[47]->m26[0];
barrier q[47],q[52],q[27];
cx q[18],q[51];
cx q[39],q[13];
h q[1];
h q[2];
h q[49];
h q[54];

// Layer 73
cx q[56],q[57];
measure q[49]->m25[0];
barrier q[49],q[13],q[32];
measure q[54]->m33[0];
barrier q[54],q[16],q[43];
h q[51];
if(m26==1) cx q[52],q[27];
h q[37];
h q[18];
if(m26==1) x q[47];

// Layer 74
cx q[57],q[53];
cx q[56],q[59];
measure q[51]->m29[0];
barrier q[51],q[30],q[1];
measure q[37]->m31[0];
barrier q[37],q[44],q[6];
if(m25==1) cx q[13],q[32];
if(m33==1) cx q[16],q[43];
h q[27];
if(m25==1) x q[49];
if(m33==1) x q[54];

// Layer 75
h q[59];
h q[53];
if(m29==1) cx q[30],q[1];
cx q[13],q[52];
if(m31==1) cx q[44],q[6];
h q[56];
h q[57];
h q[32];
h q[43];
if(m29==1) x q[51];
if(m31==1) x q[37];

// Layer 76
measure q[53]->m30[0];
barrier q[53],q[60],q[2];
measure q[59]->m27[0];
barrier q[59],q[38],q[41];
measure q[56]->m28[0];
barrier q[56],q[39],q[22];
measure q[57]->m32[0];
barrier q[57],q[45],q[18];
h q[1];
cx q[52],q[43];
cx q[13],q[7];
h q[6];

// Layer 77
if(m30==1) cx q[60],q[2];
if(m27==1) cx q[38],q[41];
if(m28==1) cx q[39],q[22];
cx q[52],q[44];
if(m32==1) cx q[45],q[18];
cx q[1],q[30];
if(m27==1) x q[59];
if(m28==1) x q[56];
if(m30==1) x q[53];
if(m32==1) x q[57];

// Layer 78
h q[2];
cx q[60],q[32];
h q[41];
h q[22];
h q[18];
cx q[30],q[6];

// Layer 79
cx q[1],q[2];
cx q[52],q[41];
cx q[60],q[27];
cx q[32],q[22];
cx q[30],q[18];

// Layer 80
cx q[32],q[52];
cx q[2],q[45];
cx q[1],q[60];
cx q[27],q[16];

// Layer 81
cx q[2],q[44];
cx q[32],q[16];
cx q[30],q[27];
cx q[13],q[1];
cx q[60],q[38];

// Layer 82
cx q[2],q[39];
cx q[60],q[32];
cx q[27],q[6];
cx q[1],q[41];
cx q[7],q[13];

// Layer 83
cx q[52],q[2];
cx q[32],q[6];
cx q[1],q[39];
cx q[60],q[18];
cx q[27],q[38];
cx q[13],q[7];

// Layer 84
cx q[30],q[52];
cx q[27],q[2];
cx q[60],q[0];
cx q[32],q[3];

// Layer 85
cx q[52],q[4];
cx q[27],q[5];
cx q[2],q[1];
cx q[0],q[60];
cx q[3],q[32];
cx q[6],q[30];

// Layer 86
cx q[4],q[52];
cx q[5],q[27];
