#include "oplsaa.ff/forcefield.itp"

[ atomtypes ]
; name  at.num  mass  charge  ptype  sigma  epsilon
DUM     1000   1.000   0.0     A      0.0    0.0

[ moleculetype ]
LIG      1

[ atoms ]
   1   DUM   1   LIG    LIG1     1    0.0

%DIR%
[ system ]
t

[ molecules ]
LIG 1
