import scipy.io as sio
import math
import scipy.spatial.distance as distance
import numpy 
import scipy.stats
import time 
import matplotlib.pyplot as plt
import argparse

from collections import namedtuple
from multiprocessing import Pool
from functools import reduce    

from  gpu_script import gpu_execute
from  thread_script import compute_parallel


Range = namedtuple("Range",
                   [
                       'data',
                       'nnz',
                       'col',
                       'row']
)


manhattan = lambda x,y: (max(math.fabs(x[0]-y[0]), math.fabs(x[1]-y[1])))

TwoDimensionalHistogram = namedtuple(
    "TwoDimensionalHistogram",
    [
        'matrix',
        'height',
        'width',
        'H',
        'W',
        'h',
        'w'
    ]
)

Differential = namedtuple(
    "Differential",
    [
        'matrix', 'm0','m1', 's0','s1', 'k', 
        'height', 'mh','sh', 
        'width',  'mw', 'sw'
    ]
)

parameters = [
    ("-f", "--file",       str,None,    'store',"Input matrix"),
    ("-d", "--device",     int,0,       'store',"GPU Device number "),
    ("-s", "--save",       str,None,    'store',"Output matrix"),
    ("-csv", "--csvfile",  str,None,    'store',"Input matrix"),
    ("-o", "--pngfile",    str,None,    'store',"Write Graphs in PNG files"),
    ("-m", "--method",     str,None,    'store',"Method"),
    ("-vis", "--visualize",  bool,False,    'store_true',"visualize in pictures"),
    ("-vvis", "--vvisualize",  bool,False,    'store_true',"visualize in pictures"),
]


def default_compiler_arg_parser(params=parameters):
    # NOTE: Not all arguments are passed as separate variables to backend functions.
    # Removing a line here may cause errors until we can completely remove the args parameter from backend functions

    parser = argparse.ArgumentParser()
    for x in params:
        #print("Adding arguments:",x)
        if x[2] is bool:
            if x[0] is not None:
                parser.add_argument(x[0], x[1], default=x[3], action=x[4], help=x[5])
            else:
                parser.add_argument(x[1], default=x[3], action=x[4], help=x[5])
        elif x[0] is not None:
            parser.add_argument(x[0], x[1], type=x[2], default=x[3], action=x[4], help=x[5])
        else:
            parser.add_argument(x[1], type=x[2], default=x[3], action=x[4], help=x[5])
    return parser
                                    

def pairs(W):
    D = numpy.zeros(W.nnz*2,dtype='int')
    D = D.reshape(W.nnz,2)
    for i in range(0,W.nnz):
        D[i,:] = [W.col[i],W.row[i]]
    #print("done pairing")
    #print(D.shape,W.nnz*(W.nnz-1)/2)
    col = (min(W.col),max(W.col))
    row = (min(W.row),max(W.row))
    return Range(D,W.nnz,col,row)

###
## Given a vector v, we define b the boundary of the shuffle and we
## merge, this is like the card shuffle. You can randomize it by
## permuting the contents of each part
###
def shuffy(v,b,t,pre=False):
    #print("shuffy", len(v),b,t)
    L    = numpy.arange(t,dtype='int')
    Low  = numpy.arange(0,b)
    High = numpy.arange(b,t)

    if pre: numpy.random.shuffle(Low)
    if pre: numpy.random.shuffle(High)
    l = 0
    h = 0
    
    for m in range(0,t):
        if l>=len(Low) or h>=len(High):
            break
        if m%2==0:
            L[m]=Low[l]
            l+=1
        else :
            L[m]=High[h]
            h+=1
    #print(m,l,h,t)
    while l<len(Low):
         L[m]=Low[l]
         l+=1
         m+=1
    while h<len(High):
         L[m]=High[h]
         h+=1
         m+=1
        
    for i in range(0,len(v)):
        v[i] = L[v[i]]
    return L

## 2D and 1D hierarchical entropy
def hier_entropy(Q,least=4):

    LL = min(least,int(math.ceil(math.log(Q.matrix.shape[0],2))))
    HL = (2**LL)//2
    T = numpy.zeros(HL*HL*LL,dtype='double').reshape(LL,HL,HL)

    ## 2D hierarchical entropy
    SS = sum(Q.matrix.flatten())
    for i in range(0,LL):
        J = 2**(i)
        JH = int(math.ceil(Q.matrix.shape[0]/J))
        #print(J,JH,J*JH)
        for j in range(0,J):
            for k in range(0,J):

                if (j*JH)>Q.matrix.shape[0] or (k*JH)>Q.matrix.shape[1]:
                    continue
                G = Q.matrix[(j*JH):min(((j+1)*JH),Q.matrix.shape[0]),(k*JH):min(((k+1)*JH),Q.matrix.shape[1])].flatten()/SS
                G = G*numpy.log(G)
                G = G[~numpy.isnan(G)]
                
                re = -sum(G)
                T[i,j,k] = re
    
    ## Height hierarchical entropy
    LL = min(least,int(math.ceil(math.log(Q.height.shape[0],2))))
    HL = (2**LL)//2    
    H = numpy.zeros(HL*LL,dtype='double').reshape(HL,LL)

    for i in range(0,LL):
        J = 2**(i)
        JH = int(math.ceil(Q.height.shape[0]/J))
        for j in range(0,J):
            if (j*JH)>Q.height.shape[0]:
                continue

            G = Q.height[(j*JH):min(((j+1)*JH),Q.height.shape[0])]/SS
            H[j,i] = -sum(G*numpy.log(G))

    ## width hierarchical entropy 
    LL = min(least,int(math.ceil(math.log(Q.width.shape[0],2))))
    HL = (2**LL)//2        
    W = numpy.zeros(HL*LL,dtype='double').reshape(LL,HL)

    for i in range(0,LL):
        J = 2**(i)
        JH = int(math.ceil(Q.width.shape[0]/J))
        #print(J,JH,J*JH)
        for j in range(0,J):
            if (j*JH)>Q.width.shape[0]:
                continue
            G = Q.width[(j*JH):min(((j+1)*JH),Q.width.shape[0])]/SS
            W[i,j] = -sum(G*numpy.log(G))
            
    return (T,H,W)
    
## vistualize the T matrix above
def ent_2d_visualize(T,name=None):
    plt.clf()
    for i in range(0,T.shape[0]):
        ax1 = plt.subplot(2,T.shape[0]/2,i+1)
        ax1.imshow(T[i], cmap='hot', interpolation='nearest') #ax1.set_title("2D hisotgram")
    if name: plt.savefig(name,bbox_inches='tight')
    else: plt.show()
## visualize the H and W above
def ent_visualize_R(T,name=None):
    plt.clf()
    ax1 = plt.subplot(111)
    ax1.imshow(T, cmap='hot', interpolation='nearest')    #ax1.set_title("2D hisotgram")
    if name: plt.savefig(name,bbox_inches='tight')
    else: plt.show()

## visualize the output of hier_entropy
def ent_visualize(R,name=None):
    ent_2d_visualize(R[0],"2d-"+name)
    ent_visualize_R(R[1],"h-"+name)
    ent_visualize_R(R[2],"w-"+name)

## computation of gradient of a matrix.  thios should help to find the
## places for random shuffles.
def gradients(his):

    D2 = numpy.gradient(his.matrix,his.h,his.w)
    ## we remove the boundary
    D2M0 = numpy.mean(D2[0][1:-1,1:-1])
    D2V0 = numpy.var(D2[0][1:-1,1:-1])
    D2M1 = numpy.mean(D2[1][1:-1,1:-1])
    D2V1 = numpy.var(D2[1][1:-1,1:-1])

    K = numpy.mean(numpy.dot((D2[0][1:-1,1:-1]-D2M0),(numpy.transpose(D2[1][1:-1,1:-1]-D2M1))))
    
    DH = numpy.gradient(his.height,his.h)
    DHM = numpy.mean(DH[1:-1]); DHV = numpy.var(DH[1:-1])

    DW = numpy.gradient(his.width,his.w)
    DWM = numpy.mean(DW[1:-1]); DWV = numpy.var(DW[1:-1])
    D = Differential(D2,D2M0,D2M1,D2V0,D2V1,K,
                     DH,DHM,DHV,
                     DW,DWM,DWV)
    return D

def visualize(his,name=None):

    plt.clf()
    ax1 = plt.subplot(212)
    ax1.imshow(his.matrix, cmap='hot', interpolation='nearest')
    #ax1.set_title("2D hisotgram")

    ax2 = plt.subplot(221)
    ax2.bar(numpy.arange(len(his.height)),his.height)
    ax2.set_title("height histogram")

    ax3 = plt.subplot(222)
    plt.bar(numpy.arange(len(his.width)),his.width)
    ax3.set_title("width histogram")
    
    if name: plt.savefig(name,bbox_inches='tight')
    else: plt.show()
    

def visualize_grad(his,name=None):

    plt.clf()
    ax1 = plt.subplot(221)
    ax1.imshow(his.matrix[0], cmap='hot', interpolation='nearest')
    ax1.set_title("h gradient")
    ax_1 = plt.subplot(222)
    ax_1.imshow(his.matrix[1], cmap='hot', interpolation='nearest')
    ax_1.set_title("w gradient")

    ax2 = plt.subplot(223)
    ax2.bar(numpy.arange(len(his.height)),his.height)
    ax2.set_title("height gradient")

    ax3 = plt.subplot(224)
    plt.bar(numpy.arange(len(his.width)),his.width)
    ax3.set_title("width gradient")
    
    if name: plt.savefig(name,bbox_inches='tight')
    else:  plt.show()
    
## 2D, Height, and Width histogram
def spatial_hist(M,factor=1):
    H,W = M.shape
    ratio = H/W
    A = W*H
    nnz = M.nnz

    ## LL*nnz should cover the whole area A
    LL= (factor*factor)*A//nnz

    h = int(math.sqrt(LL*ratio))
    w = LL//h

    D = numpy.zeros(int(math.ceil(H/h))*int(math.ceil(W/w)),dtype='double').reshape(int(math.ceil(H/h)),int(math.ceil(W/w)))
    DH = numpy.zeros(int(math.ceil(H/h)),dtype='double')
    DW = numpy.zeros(int(math.ceil(W/w)),dtype='double')

    for i in range(0,nnz):
        c = (M.col[i]//w)
        r = (M.row[i]//h)
        D[r-1,c-1] += 1
        DH[r-1] +=1
        DW[c-1] +=1

    D = D +(LL/A)
    DH = DH + (LL/A)
    DW = DW + (LL/A)
    return TwoDimensionalHistogram(D,DH,DW,H,W,h,w)

def hist(W, bins=50,parts=128):
    P = pairs(W)
    for i in range(0,1):
        L = i*P.nnz//parts
        R = min( (i+1)*P.nnz//parts,P.nnz)-1
        distances = distance.pdist(P.data[L:R],metric='cityblock')
        
        H=  list(
            numpy.histogram(distances,bins = max(P.col) + max(P.row)+1, range = (0.0, 1.0*max(P.col) + max(P.row)))
        )

    LH = list(H[1])
    LH.pop(0)
    print("First level")
    for i in range(1,parts):
        L = i*P.nnz//parts
        R = min( (i+1)*P.nnz//parts,P.nnz)-1
        distances = distance.pdist(P.data[L:R], metric='cityblock')
        HQ =   numpy.histogram(distances,bins = max(P.col) + max(P.row)+1,range = (1.0, 1.0*max(P.col) + max(P.row)))
        H[0]  = numpy.add(H[0],HQ[0])
        print(i,"Entropy",scipy.stats.entropy(1.0*H[0]/sum(H[0]),LH))

    print("Second level")
    for j in range(0,parts-1):
        L = j*P.nnz//parts
        R = min( (j+1)*P.nnz//parts,P.nnz)-1
        for i in range(j,parts):
            L1 = i*P.nnz//parts
            R1 = min( (i+1)*P.nnz//parts,P.nnz)-1
            distances = distance.cdist(P.data[L:R],P.data[L1:R1],metric='cityblock')
            HQ =   numpy.histogram(distances, bins = max(P.col) + max(P.row)+1, range = (1.0, 1.0*max(P.col) + max(P.row)))
            H[0]  = numpy.add(H[0],HQ[0])
            print(j,"Entropy",scipy.stats.entropy(1.0*H[0]/sum(H[0]),LH))

    return H


def autodistance(I):
    L,R,i = I
    #print("start",L,R)
    distances = distance.pdist(P.data[L:R],metric='cityblock')
    H= numpy.histogram(distances,bins = max(P.col) + max(P.row)+1, range = (0.0, 1.0*max(P.col) + max(P.row)))
    print("done",i)
    return H


def crossdistance(I):
    L,R = I[0]
    L1,R1 = I[1]
    #print("start",L,R, L1,R1)
    distances = distance.cdist(P.data[L:R],P.data[L1:R1],metric='cityblock')
    H =  numpy.histogram(distances, bins = max(P.col) + max(P.row)+1,range = (1.0, 1.0*max(P.col) + max(P.row)))
    print("done",I[2])
    return H


def hist2(P,parts=128,C=12):
    I = []
    
    # auto
    for i in range(1,parts):
        L = i*P.nnz//parts
        R = min( (i+1)*P.nnz//parts,P.nnz)-1
        I.append([L,R,i])

    #cross
    J = []
    for j in range(0,parts-1):
        L = j*P.nnz//parts
        R = min( (j+1)*P.nnz//parts,P.nnz)-1
        
        for i in range(j,parts):
            L1 = i*P.nnz//parts
            R1 = min( (i+1)*P.nnz//parts,P.nnz)-1
            J.append([[L,R],[L1,R1],len(J)])

    def combine_hist(H,HQ):
        return   (numpy.add(H[0],HQ[0]),H[1])


    with Pool(C) as p:
        print("auto")
        Hs =  p.map(autodistance,I)
        print("partial reduce")
        P = reduce(combine_hist,Hs)
        print(P)
        LH = list(P[1])
        LH.pop()
        print(len(P[0]), len(P[1]),len(LH))

        print(numpy.dot(P[0]/sum(P[0]),LH))
        print(j,"Entropy",scipy.stats.entropy(1.0*P[0]/sum(P[0]),None))
        sys.exit()
        
        print("cross")
        H2S = p.map(crossdistance,J)

        print("reduce")
        P = reduce(combine_hist,[P]+H2S)
        print(P)
        print(sum(P[0]))
        
        print(j,"Entropy",scipy.stats.entropy(1.0*P[0]/sum(P[0]),None))
        
    

def measure(A, IN=10, device=0) :
    
    B = numpy.ones(A.shape[1])
    b = time.time();
    for ll in range(0,IN):
        Rf = A*B
    e = time.time();
    coo = (e-b)/IN
    nnz = A.nnz
    coogflops = (nnz/coo)/1000000000
    AC= A.tocsr()
    b = time.time();
    for ll in range(0,IN):
        Rf = AC*B
    e = time.time(); 
    csr = (e-b)/IN
    csrgflops = (nnz/csr)/1000000000

    return "COO GFLOPS {0:5.2f} CSR GFLOPS {1:5.2f} ".format(coogflops,csrgflops)  

def measure_p(filename) :
    
    return compute_parallel([filename])
    

def gpu_measure(filename, device=0) :
    #import pdb; pdb.set_trace()
    R : dict = {device: {'s' : {}, 'd' : {}}}
    R = gpu_execute(device,filename,R)

    
    try :    scsrflops = R[device]['s']['csr'] ['GFlops']
    except : scsrflops = 0.0
    try :    scooflops = R[device]['s']['coo'] ['GFlops']
    except : scooflops = 0.0
    try :    dcsrflops = R[device]['d']['csr'] ['GFlops']
    except : dcsrflops = 0.0
    try :    dcooflops = R[device]['d']['coo'] ['GFlops']
    except : dcooflops = 0.0
    #import pdb; pdb.set_trace()        
    S =    "GPU COO S-GFLOPS {0:5.2f} D-GFLOPS {1:5.2f} CSR S-GFLOPS {2:5.2f} D-GFLOPS {3:5.2f} ".format(
        scooflops,dcooflops,scsrflops,dcsrflops
    )

    return S

def distance_matrix(args):
    W = sio.mmread(args.file)
    P = pairs(W)
    print(P)
    hist2(P,50,24)

def search(args):
    
    extra = False
    
    filename =args.file
    marker = "/" 
    
    location = filename[:filename.rfind(marker)]
    name     = filename[filename.rfind(marker)+1:]
    wrt = location+"/SHUFFLED/"
    ResultsHeader="name,entropy,"+\
        "e"+",e".join(str(i) for i in range(0,8*8)) +\
        ",finalEntropy,"+\
        "f"+",f".join(str(i) for i in range(0,8*8))
    Results = [args.file]
    W = sio.mmread(args.file)
    Q = spatial_hist(W)
    if args.visualize or args.vvisualize: visualize(Q,name+".regular.png")
    D = gradients(Q)
    if args.visualize: visualize_grad(D,"regular-gradient.png")
    Ent = scipy.stats.entropy(Q.matrix.flatten(),None)
    
    if extra:
        print("Gradient d",D.m0,D.m1, D.s0,D.s1, D.k)
        print("Entropy  h",scipy.stats.entropy(Q.height.flatten(),None))
        print("Gradient h",D.mh,D.sh)
        print("Entropy  w",scipy.stats.entropy(Q.width.flatten(),None))
        print("Gradient w",D.mw,D.sw)
    R = hier_entropy(Q)
    Results.append(Ent)
    for e  in R[0][-1,:,:].flatten():
        Results.append(e)
    sio.mmwrite(wrt+"0_"+name,W)
    print("{:25s} {:7s}".format(name,str(W.dtype)),
          "Entropy      d {:5.2f} ".format(Ent),
          "time",measure(W,1000),
          gpu_measure(wrt+"0_"+name,args.device),
          measure_p(wrt+"0_"+name))
    if args.visualize: ent_visualize(R,"regular.png")
    WT = W.copy()

    ## regular shuffle
    for i in range(0,1):
        
        
        numpy.random.shuffle(W.row)
        Q = spatial_hist(W)
        if args.visualize: visualize(Q,"shuffle.png")
        D = gradients(Q)
        if args.visualize: visualize_grad(D,"shuffle-gradient.png")
        
        
        if extra:
            print("Gradient pre-d",D.m0,D.m1, D.s0,D.s1, D.k)
            print("Entropy  pre-h",scipy.stats.entropy(Q.height.flatten(),None))
            print("Gradient pre-h",D.mh,D.sh)
            print("Entropy  pre-w",scipy.stats.entropy(Q.width.flatten(),None))
            print("Gradient pre-w",D.mw,D.sw)
        
        sio.mmwrite(wrt+"1_"+name,W)
        print("{:25s} {:7s}".format(name,str(W.dtype)),
              "Entropy  pre-d {:5.2f} ".format(scipy.stats.entropy(Q.matrix.flatten(),None)),
              "time",measure(W,1000),
              gpu_measure(wrt+"1_"+name,args.device),
              measure_p(wrt+"1_"+name)
        )
        R = hier_entropy(Q)
        if args.visualize:  ent_visualize(R,"shuffle.png")

    ## targeted row shuffle
    S = False
    a = None
    if D.sh>0:
        a = numpy.abs((D.height[1:-1]-D.mh)/math.sqrt(D.sh))

    W = WT.copy()
    if a is not None and (5*a>0).any():
        
        S = True
        mx = max(a)
        for i in range(0,len(a)):
            if a[i] == mx:
                break
        #print("i h ", i,Q.h)
        shuffy(W.row,(i+1)*Q.h,Q.H,True)
        Q = spatial_hist(W)
        if args.visualize: visualize(Q,"H-shuffle.png")
        D = gradients(Q)
        if args.visualize: visualize_grad(D,"H-shuffle-gradient.png")
        if extra:
            print("H Gradient d",D.m0,D.m1, D.s0,D.s1, D.k)
            print("H Entropy  h",scipy.stats.entropy(Q.height.flatten(),None))
            print("H Gradient h",D.mh,D.sh)
            print("H Entropy  w",scipy.stats.entropy(Q.width.flatten(),None))
            print("h Gradient w",D.mw,D.sw)
        sio.mmwrite(wrt+"2_"+name,W)
        print("{:25s} {:7s}".format(name,str(W.dtype)),
              "H Entropy    d {:5.2f} ".format(scipy.stats.entropy(Q.matrix.flatten(),None)),
              "time",measure(W,1000),
              gpu_measure(wrt+"2_"+name,args.device),
              measure_p(wrt+"2_"+name))
        R = hier_entropy(Q)
        if args.visualize: ent_visualize(R,"H-shuffle.png")

    ## targeted col shuffle
    a = None
    if D.sw>0:
        a = numpy.abs((D.width[1:-1]-D.mw)/math.sqrt(D.sw))

    #W =	WT.copy()
    if a is not None and (5*a>0).any():
        S = True
        mx = max(a)
        for i in range(0,len(a)):
            if a[i] == mx:
                break
        #print("i", i,Q.h)
        shuffy(W.col,(i+1)*Q.w,Q.W,True)
        Q = spatial_hist(W)
        if args.visualize: visualize(Q,"W-shuffle.png")
        D = gradients(Q)
        if args.visualize: visualize_grad(D,"W-shuffle-gradient.png")



        if (False):
            print("W Gradient d",D.m0,D.m1, D.s0,D.s1, D.k)
            print("W Entropy  h",scipy.stats.entropy(Q.height.flatten(),None))
            print("W Gradient h",D.mh,D.sh)
            print("W Entropy  w",scipy.stats.entropy(Q.width.flatten(),None))
            print("W Gradient w",D.mw,D.sw)
        R = hier_entropy(Q)
        if args.visualize: ent_visualize(R,"W-shuffle.png")
        sio.mmwrite(wrt+"3_"+name,W)
        print("{:25s} {:7s}".format(name,str(W.dtype)),
              "W Entropy    d {:5.2f} ".format(scipy.stats.entropy(Q.matrix.flatten(),None)),"time",
              measure(W,1000),gpu_measure(wrt+"3_"+name,args.device),
              measure_p(wrt+"3_"+name)
        )
        
    W =	WT.copy()
    ## regular shuffle
    for i in range(0,1):
        numpy.random.shuffle(W.col)
        numpy.random.shuffle(W.row)
        Q = spatial_hist(W)
        if args.visualize: visualize(Q,"row-column-shuffle.png")
        D = gradients(Q)
        if args.visualize: visualize_grad(D,"row-column-shuffle-gradient.png")
        Ent = scipy.stats.entropy(Q.matrix.flatten(),None)
                
        if extra:
            print("Gradient post-d",D.m0,D.m1, D.s0,D.s1, D.k)
            print("Entropy  post-h",scipy.stats.entropy(Q.height.flatten(),None))
            print("Gradient post-h",D.mh,D.sh)
            print("Entropy  post-w",scipy.stats.entropy(Q.width.flatten(),None))
            print("Gradient post-w",D.mw,D.sw)
        
        R = hier_entropy(Q)
        if args.visualize:  ent_visualize(R,"row-column-shuffle.png")
        Results.append(Ent)
        for e  in R[0][-1,:,:].flatten(): 
            Results.append(e)
        sio.mmwrite(wrt+"4_"+name,W)
        print("{:25s} {:7s}".format(name,str(W.dtype)),
              "Entropy post   {:5.2f} ".format(Ent),"time",measure(W,1000),
              gpu_measure(wrt+"4_"+name,args.device),
              measure_p(wrt+"4_"+name))
    print("------------------")
    if args.csvfile:
        print(len(ResultsHeader.split(",")),len(Results))
        with open(args.csvfile,"w") as F:
            F.write(ResultsHeader)
            F.write(",".join([str(i) for i in Results]))
            F.close()
    
    if args.save:
        sio.mmwrite(args.save,W)
        
        
if __name__ == '__main__':


    parser = default_compiler_arg_parser()
    args = parser.parse_args()
        
    search(args)



        


    
    
