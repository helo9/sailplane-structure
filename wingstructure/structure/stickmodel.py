import numpy as np
from matplotlib import pyplot as plt


class Stickmodel:
    """Object for representation and calculation of unbranched Beam structures"""

    def __init__(self, nodes:np.ndarray, forces:dict=None, moments:dict=None, prescribed:dict=None,
                 use_local_coordinate_system:bool=True, do_auto_updates:bool=True):
        
        self.nodes = nodes
        self.acting_forces = {} if forces is None else forces
        self.acting_moments = {} if moments is None else moments
        self.prescribed = {} if prescribed is None else prescribed

        self.resulting_forces = None
        self.resulting_moments = None

        self._use_local_coordinate_system = use_local_coordinate_system

        self.auto_updates = True

    def add_discreteforces(self, name:str, discrete_forces:np.ndarray):
        if name in self.acting_forces.keys():
            raise AttributeError(f'forces with key {name} exist already!')

        self.acting_forces[name] = discrete_forces

        self._update()

    def add_discretemoments(self, name:str, discrete_moments:np.ndarray):
        if name in self.acting_moments.keys():
            raise AttributeError(f'moments with key {name} exist already!')

        self.acting_moments[name] = discrete_moments

        self._update()

    def set_local_coordinatesystem(self, use_local_coordinate_system:bool):
        self._use_local_coordinate_system = use_local_coordinate_system

        self._update()

    def _update(self):
        if self.auto_updates:
            try:
                self.update()
            except:
                self.resulting_moments = None
                self.resulting_moments = None

    def update(self):

        n = len(self.nodes)
        A = np.zeros([6*n,6*n])
        b = np.zeros(6*n)

        # equilibrium conditions (-force_node0 + force_node1 = 0, just the same for moments)
        for i in range(6*(n-1)):
            A[i][i] = -1
            A[i][i+6] = 1

        # moments resulting from internal forces
        for i in range(n-1):
            lx, ly, lz = self.nodes[i+1] - self.nodes[i]
            idx = 6*i

            ## cross product lever x internal force
            A[idx+3][idx+7] = -lz
            A[idx+3][idx+8] = ly

            A[idx+4][idx+6] = lz
            A[idx+4][idx+8] = -lx

            A[idx+5][idx+7] = lx
            A[idx+5][idx+6] = -ly

        # equations for prescribed values
        for node, prescribed_values in self.prescribed.items():
            for i, prescribed_value in enumerate(prescribed_values):
                if prescribed_value is np.NaN:
                    continue
                A[6*(n-1) + i][6*node + i] = 1
                b[6*(n-1) + i] = -prescribed_value

        try:
            acting_force_array = np.vstack([
                part for part in self.acting_forces.values()
            ])

            acting_moment_array = np.vstack([
                part for part in self.acting_moments.values()
            ])
        except:
            raise ValueError("forces and/or moments are not given in correct form")

        # external loads
        for i in range(n-1):
            # forces
            forces_on_current_element = \
                 acting_force_array[acting_force_array[:,-1] == i]
            for l in forces_on_current_element:
                # force
                b[6*i:6*i+3] += l[3:-1]
        
                # resulting moment (cross product)
                M = np.cross(l[:3] - self.nodes[i], l[3:-1]) 
                b[6*i+3:6*i+6] += M

            # moments
            moments_on_current_element = \
                acting_moment_array[acting_moment_array[:,-1] == i]
            for m in moments_on_current_element:
                b[6*i+3:6*i+6] += m[:-1]

        # solve the linear equation system
        x = np.linalg.solve(A, -b)

        x = np.reshape(x, (len(x)//6, 6))

        if self._use_local_coordinate_system:
            x = internalloads2spar(x, self.nodes)
        
        self.resulting_forces = x[:, :3]
        self.resulting_moments = x[:, 3:]

    def plot_acting_loads(self, fig=None, clear=True):
        if fig is None:
            fig = plt.figure()
        elif clear:
            plt.clf()
            
        ax = fig.gca(projection='3d')
        
        self._plot_nodes(ax)
        self._plot_forces(ax)
        
        plt.show()

    def _plot_nodes(self, ax):
        
        X = self.nodes[:, 0]
        Y = self.nodes[:, 1]
        Z = self.nodes[:, 2]
        
        ax.plot(X, Y, Z, 'k+-')

        max_range = np.array([X.max()-X.min(), Y.max()-Y.min(), Z.max()-Z.min()]).max() / 2.0

        mid_x = (X.max()+X.min()) * 0.5
        mid_y = (Y.max()+Y.min()) * 0.5
        mid_z = (Z.max()+Z.min()) * 0.5
        ax.set_xlim(mid_x - max_range, mid_x + max_range)
        ax.set_ylim(mid_y - max_range, mid_y + max_range)
        ax.set_zlim(mid_z - max_range, mid_z + max_range)

    def _plot_forces(self, ax):
        for i, (force_type, forces) in enumerate(self.acting_forces.items()):
            print(f'{force_type} - {i}')
            ax.quiver(*forces[:,:3].T, *forces[:,3:-1].T*1e-2, color='C{:02d}'.format(i))     

def calc_lineloadresultants(ys, q):
    """Calculate resultants of loads for piecewise linear load distributin
    
    Parameters
    ----------
    ys : numpy array, list
        grid points
    q : numpy array, list
        field values
    
    Returns
    -------
    array
        discrete resultant forces and coordinates [[x, y, z, Q_x, Q_y, Q_z], ...]
    """

    # calculate element lengths
    Δys = np.diff(ys)
    
    # initialize arrays for
    
    # force resultants
    Q = []
    
    # resultants attack point
    y_res = []

    # segments force resultant acts on
    segs = []
    
    # iterate over parts of wing
    for i in range(1,len(ys)):
        
        if q[i]==0 and q[i-1]==0:
            # Nothing to do..
            continue
        elif (q[i]>=0 and q[i-1]>=0) or (q[i]<=0 and q[i-1]<=0):
            # trapez rule to get resultant
            Q.append(Δys[i-1] * (q[i]+q[i-1])/2)
            # center of trapez as attack point of resultant
            y_res.append(ys[i-1] + np.abs(Δys[i-1])/3 * np.abs((q[i-1]+2*q[i]) / (q[i]+q[i-1])))
            segs.append(i-1)
        else:
            # sign changes from q[i-1] to q[i]
            # cannot be captured by single resultant within this section
            # -> resultants of the two triangles are used
            y_0 = ys[i-1] + Δys[i-1] * np.abs(q[i]/q[i-1]) / (1 + np.abs(q[i]/q[i-1]))

            #print(f'y_0 = {y_0, Δys, ys[i-1]}')

            # left triangle
            Q.append(0.5*(y_0-ys[i-1])*q[i-1])
            y_res.append(ys[i-1] + (y_0 - ys[i-1])/3.0)
            segs.append(i-1)

            # right triangle
            Q.append(0.5*(ys[i] - y_0)*q[i])
            y_res.append(ys[i] - (ys[i]-y_0)/3.0)
            segs.append(i-1)
    
    loads = np.zeros((len(y_res), 7))
    loads[:, 1] = y_res
    loads[:, -2] = Q
    loads[:, -1] = segs
    
    return loads


def calc_discretemoments(ys, m, axis=0):
    """Determine discrete moments from moment distribution
    
    Parameters
    ----------
    ys : array
        grid points
    m : array
        moment distribution values
    axis : int, optional
        axis the moments act, by default 0
    
    Returns
    -------
    array
        discrete moemnts
    """

    m = np.array(m)

    # calculate element lengths
    Δys = np.diff(ys)

    M = np.zeros((len(Δys), 4))
    M[:, axis] = 0.5 * (m[1:]+m[:-1]) * Δys

    M[:, 3] = np.arange(0,len(Δys))

    return M


def transform_forces(flatwing, forces, rotate=False, inline=False):
    """transform forces from flat to three dimensional wing
    
    Parameters
    ----------
    flatwing: FlatWing
        instance of flattend wing
    forces : array
        resultant loads array [[x, y, z, Q_x, N, Q_y]..]
    rotate : bool, optional
        switch for rotation of loads, by default False
    inline : bool, optional
        modify forces if True or return new transformed_forces array

    Returns
    -------
    array
        transformed_forces if inline=False

      ..caution::
        when using inline option make sure forces have floating point dtype 
    """

    ys = flatwing.ys
    dy = np.diff(ys)

    if not inline:
        forces = np.array(forces, copy=True, dtype=np.float)

    for j, load in enumerate(forces):
        y = load[1]

        # find last value smaller than y in ys
        i = np.searchsorted(ys, np.abs(y))

        # position in 3D
        pos1 = np.array(flatwing.basewing.sections[i-1].pos)
        pos2 = np.array(flatwing.basewing.sections[i].pos)

        # calculate relativ position between sections
        f = (np.abs(y)-ys[i-1])/dy[i-1]

        # interpolate position
        forces[j, :3] = pos1 + (pos2-pos1) * f

        if rotate:
            rotmat = np.eye(3)

            n0 = np.array((0,1,0))
            n1 = pos2-pos1
            n1 /= np.linalg.norm(n1)

            cosφ = np.dot(n0, n1)
            sinφ = np.sqrt(1-cosφ**2)

            rotmat[1:,1:] = [[cosφ, sinφ], [-sinφ, cosφ]]

            if y<0.0:
                rotmat = rotmat.T

            forces[j, 3:-1] = forces[j, 3:-1] @ rotmat

    if not inline:
        return forces


def transform_moments(flatwing, moments, ys, inline=False):
    """Transform moments into wing coordinate system
    
    Parameters
    ----------
    flatwing : FlatWing
        discription of flattend wing
    moments : array
        discrete moments [[Mx, My, Mz, segment],...]
    ys: array
        grid points
    inline: bool
        modify moments or return new array

    Returns
    -------
    array
        transformed moments, only if inline=False
    """

    from scipy.interpolate import interp1d

    if inline:
        transformed_moments = moments
    else:
        transformed_moments = np.copy(moments)

    positions = np.array([(sec.pos.y, sec.pos.z) for sec in flatwing.basewing.sections])

    normals = np.diff(positions, axis=0, append=0.0)
    normals[:-1,:] /= np.linalg.norm(normals[:-1,:])

    cosφ = interp1d(flatwing.ys, np.dot((1,0), normals.T), kind='previous')

    midy = ys[:-1] + np.diff(ys)/2

    for i, (_,_,_,seg_id) in enumerate(moments):
        y = midy[int(seg_id)]
        ccosφ = cosφ(abs(y))
        csinφ = np.sqrt(1-ccosφ**2)

        rotmat = np.eye(3)
        rotmat[1:,1:] = [[ccosφ, csinφ], [-csinφ, ccosφ]]

        if y<0.0:
            rotmat = rotmat.T
        transformed_moments[i,:-1] = transformed_moments[i,:-1] @ rotmat
    
    if not inline:
        return transformed_moments
   

def get_nodes(wing, ys, chordpos=0.25):
    """calculate grid points from wing
    
    Parameters
    ----------
    wing : Wing
        a object describing a wing
    ys : array
        grid points on flattend span
    chordpos: float or callable
        relative position in chordwise direction, 
        callable must be vectorized!
    
    Returns
    -------
    array
        nodes [[x,y,z],...]
    """
    from numpy import diff, linalg
    from scipy.interpolate import interp1d
     
    # planform sections in yz plane
    pos_yz = np.array(
        [(sec.pos.y, sec.pos.z) for sec in wing.sections]
    )

    # calculate distances between sections
    distances = linalg.norm(np.diff(pos_yz[:,:], axis=0, prepend=0), axis=1)

    # sum um distances
    distancesums = np.cumsum(distances)
    
    print(distancesums)

    # leading edge positions
    pos = np.array(
        [(sec.pos.x, sec.pos.y, sec.pos.z) for sec in wing.sections]
    )

    if callable(chordpos):
        pos_int = interp1d(distancesums, pos, axis=0)(ys)

        pos_int[:,0] += interp1d(distancesums, wing.chords)(ys) * chordpos(ys)

        return pos_int
    else:
        # shift x coordinate
        pos[:,0] += np.array([sec.chord*chordpos for sec in wing.sections])

        return interp1d(distancesums, pos, axis=0)(ys)



def internalloads2spar(internalloads, sparnodes):
    """Transform internal loads to spar coordinate system
    
    Parameters
    ----------
    internalloads : array
        internal loads (global cartesian coordinate system)
    sparnodes : array
        coordinates of spar nodes
    
    Returns
    -------
    array
        transformed internal loads [[Qn, Q1 Q2, Mt, Mb1, Mb2], ...]
    """

    internalloads = np.copy(internalloads)
    
    for i, load in enumerate(internalloads):

        # get current spar normal

        ## if last node - use same direction vector as before
        if i == sparnodes.shape[0]-1:
            i -= 1
        
        ns = _get_normal(*sparnodes[i:i+2,:])
        
        # rotation axis
        nx = np.array([1,0,0])
        n_rot = np.cross(nx, ns)
        
        # collect all direction vectors
        n1 = ns
        n2 = rotmat2(n_rot) @ ns
        n3 = np.cross(n2, n1)

        # build rotation matrix
        rotmat = np.linalg.inv(np.vstack((n2,n1,n3)))

        # do transformation
        internalloads[i,:3] = load[:3] @ rotmat
        internalloads[i, 3:] = load[3:] @ rotmat

    return internalloads

def _get_normal(p1, p2):
    n = p2-p1
    n0 = n/np.linalg.norm(n)

    return n0

def rotmat2(rotax):
    
    n1 = rotax[0]
    n2 = rotax[1]
    n3 = rotax[2]
    
    c = np.cos(-np.pi/2)
    s = np.sin(-np.pi/2)

    R = np.array([[n1**2*(1-c)+c, n1*n2*(1-c)-n3*s, n1*n3*(1-c)+n2*s],
                [n2*n1*(1-c)+n3*s, n2**2*(1-c)+c, n2*n3*(1-c)-n1*s],
                [n3*n1*(1-c)-n2*s, n3*n2*(1-c)+n1*s, n3**2*(1-c)+c]])

    return R
