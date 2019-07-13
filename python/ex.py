import sparsecoo
import pdb
import scipy
import scipy.io as sio
import math
B = sio.mmread("bcsstk32.mtx")
A = sio.mmread("bcsstk32.mtx")
C = sio.mmread("bcsstk32.mtx")





def sparse_mm(P,C=C,A=A,B=B):


    
    AL = []
    print("Ordering A")
    for i in range(0,A.nnz):
        AL.append([A.row[i],A.col[i], i])

    AL = sorted(AL, key = lambda x: (x[0],x[1]))
    I = []
    for i in range(0,A.nnz):
        I.append(AL[i][2])
    A.row = A.row[I]
    A.col = A.col[I]
    A.data = A.data[I]

    #A.row = A.row[0:IP]
    #A.col = A.col[0:IP]
    #A.data = A.data[0:IP]


    
    print("Ordering C")
    AL = []
    for i in range(0,C.nnz):
        AL.append([C.row[i],C.col[i], i])

    AL = sorted(AL, key = lambda x: (x[0],x[1]))
    I = []
    for i in range(0,A.nnz):
        I.append(AL[i][2])
    
    C.row = C.row[I]
    C.col = C.col[I]
    C.data = C.data[I]
    #C.row = C.row[0:IP]
    #C.col = C.col[0:IP]
    #C.data = C.data[0:IP]
    print("Ordering B")
    BL = []
    for i in range(0,B.nnz):
        BL.append([B.row[i],B.col[i], i])

    BL = sorted(BL, key=lambda x: (x[0],x[1]))
    I = []
    for i in range(0,B.nnz):
        I.append(BL[i][2])
    
    B.col  = B.col[I]
    B.row  = B.row[I]
    B.data = B.data[I]

    #B.row = B.row[0:IP]
    #B.col = B.col[0:IP]
    #B.data = B.data[0:IP]

    #pdb.set_trace()

    print("Calling ")
    print(type(P),type(A.col),A.col.dtype,type(A.row),A.row.dtype,type(A.data),A.data.dtype,type(A.shape[0]),type(A.shape[1]))
    print(P,C.col.shape,C.row.shape,C.data.shape,C.shape)
    print(C.col[3],C.row[3],C.data[3])
    print(P,A.col.shape,A.row.shape,A.data.shape,A.shape)
    print(type(B.col),type(B.row),type(B.data),type(B.shape[0]),type(B.shape[1]))
    print(B.col.shape,B.row.shape,B.data.shape,B.shape)

    print("testing A",
          (A.col>A.shape[1]).any(),(A.col<0).any(),
          (A.row>A.shape[0]).any(),(A.row<0).any()
    )

    print("testing B",
          (B.col>B.shape[0]).any(),(B.col<0).any(),
          (B.row>B.shape[1]).any(),(B.row<0).any() 
    )

    print("testing C",
          (C.col>C.shape[1]).any(),(C.col<0).any(),
          (C.row>C.shape[0]).any(),(C.row<0).any() 
    )
    
    cr,cc,cv =  sparsecoo.pcoomul(
        P,
        C.col,C.row,C.data,C.shape[0],C.shape[1],
        A.col,A.row,A.data,A.shape[0],A.shape[1],
        B.row,B.col,B.data,B.shape[1],B.shape[0]    # transposeing B
    )
    print(A.shape,cr.shape,cc.shape,cv.shape)
    
    #pdb.set_trace()
    return scipy.sparse.coo_matrix((cv, (cr, cc)))



#G =sparse_mm(5000,1) #C,A,B,5000)
#print(type(G))