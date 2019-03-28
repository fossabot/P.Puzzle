import Bio.PDB as pdb
from Bio import pairwise2
#from Bio.SubsMat.MatrixInfo import blosum62
from Bio.pairwise2 import format_alignment

import os
import copy as cp
import string
import numpy as np
import itertools
import pickle
from project import *
import settings

available_chain_names = list(string.ascii_uppercase + string.ascii_lowercase + string.digits)
available_chain_names.reverse()

def Check_folder(folder):
    """If folder don't exists creates it in the actual path"""
    path = os.getcwd()

    new_path = os.path.join(path,folder)

    if not os.path.isdir(new_path):

        try:
            os.mkdir(new_path)
        except OSError:
            print ("Creation of the directory %s failed" % path)
            return False
        else:
            print ("Successfully created the directory %s " % path)

    return True

def Separate_Chains(pdb_file):
    """Separate the two chains and return their name in a list"""

    folder = "pdb_chains"

    if not Check_folder(folder):

        return False

    pdb_parser = pdb.PDBParser(PERMISSIVE=True, QUIET=True)

    pdb_structure = pdb_parser.get_structure("pdb_file", pdb_file)

    interaction = list(pdb_file[:-4].split("_")[-1]) # Obtain 2 len list with the chain names from file name, the order of the letters need match with the order in the pdb file(format= something_chains.pdb)

    if len(interaction) != 2: #if the length is not true, something goes wrong

        return error

    i=0

    for model in pdb_structure:
        for chain in model:

            id=chain.get_id()

            class chain(pdb.Select):
                def accept_chain(self, chain):
                    if chain.get_id()== id:
                        return True
                    else:
                        return False

            io = pdb.PDBIO()

            io.set_structure(pdb_structure)

            name = "%s_chain_%s.pdb" %(interaction[0] + interaction[1], interaction[i])

            file_name = os.path.join(folder,name)

            io.save(file_name, chain())

            i += 1

    return interaction

def Get_Chains(pdb_file,pairs):
    """Divide the interaction pair and return the interaction and the chains object

    Input:
    -pdb_file = target file to process
    -pairs = pairs dictionary for see if the interaction pair is already processed
    Output:
    -interaction = string containg the two chains interacting
    -pair = dictionary:
     -Keys = Chain name (extracted from the file name)
     -Values = Chain object (corresponding to the chain name by order criteria in the file)
    """

    pdb_parser = pdb.PDBParser(PERMISSIVE=True, QUIET=True)

    interaction = pdb_file[:-4].split("_")[-1] # Obtain str with the interaction from the file name, the order of the letters need match with the order in the pdb file(format= something_chains.pdb)
    # interaction = pdb_file[:-4].split("/")[-1]
    pdb_structure = pdb_parser.get_structure(interaction, pdb_file)

    print(interaction)
    if len(interaction) != 2 or interaction in pairs: #if the length is not true or the pair already exists, something goes wrong
        return error

    pair = {}

    for model in pdb_structure: #In this loop a pdb object is created with only the information of 1 chain
        for chain in model:
            model_copy = cp.deepcopy(model)
            model_copy.detach_child(chain.get_id())
            for chain_copy in model_copy:
                pair[interaction[1]] = chain_copy
            interaction = interaction[::-1]

    del pdb_structure

    return interaction, pair


def Parse_List(list):
    """Apply the Get_Chain to all the list and returns a relationship and pairs dictionary

    Relationship dictionary:
    -Keys = str with chain_name
    -Values = set of chains with relathionship with the key one

    Pairs dictionary:
    -Keys = interaction pair
    -Values = dictionary:
      -Keys = Chain name
      -Values = Chain object
    """

    pairs = {}

    RelationDict = {}

    for pdb_file in list:

        chains,pair = Get_Chains(pdb_file, pairs)

        pairs[chains] = pair

        for letter in chains:

            if letter in RelationDict:
                RelationDict[letter].add(chains[1])
            else:
                RelationDict[letter] = set([chains[1]])

            chains = chains[::-1] #reverse the order of the chains

    return RelationDict, pairs

def Delete_Folder(folder):
    """Delete all the files in a folder and the folder"""

    for generated_file in os.listdir(folder):
        file_path = os.path.join(folder, generated_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(e) #Error
            return False

    try:
        os.rmdir(folder)
    except Exception as e:
        print(e) #Error
        return False

    return True

def Collision_Check(model_atom_list,addition_atom_list, radius):
    """Return a list of tuple containing the residue id interacting and the coordinates in conflict

    input:
    -model = list of atoms take as reference for the collitions
    -addition = list of atoms being us to check against the model
    -radius = integrer required for become the empty radious (Amstrongs) around each atom
    """

    model_ns = pdb.NeighborSearch(model_atom_list)

    collisions_list=[]
    for atom in addition_atom_list:
        collision_list = model_ns.search(atom.get_coord(),radius,"R")
        collisions_list.extend([tuple([str(atom.get_parent().get_id()[1]),str(x.get_id()[1]),str(atom.get_coord())]) for x in collision_list])

    return collisions_list

def Superimpose_Chain(reference, interaction, target, pairs, collisions_accepted, radius):
    """Superimpose two chains with the same length and returns the related chain object moved accordingly

    Input:
    -reference = chain object used as reference
    -interaction = String with two chain names related between them
    -target = string chain name of the common chain
    -pairs = Pairs dictionary:
    -Keys = interaction pair
    -Values = dictionary:
      -Keys = Chain name
      -Values = Chain object
    -radius = integrer required for become the empty radious (Amstrongs) around each atom
    -collisions_accepted = number of atom collisions allowed in each join
    """

    fixed_atoms, mobile_atoms = Check_Similarity(reference, pairs[interaction][target])

    sup = pdb.Superimposer()#apply superimposer tool
    sup.set_atoms(fixed_atoms, mobile_atoms)#set both lists of atoms here to get rotation
    rotran = sup.rotran

    mobile_chain_name = interaction.replace(target,"",1)# Obtain the chain name of the mobile one

    mobile_chain = cp.deepcopy(pairs[interaction][mobile_chain_name])

    mobile_chain.transform(rotran[0],rotran[1])

    model_atom_list = []
    for chain in reference.get_parent():
        model_atom_list.extend(chain.get_atoms())

    addition_atom_list = list(mobile_chain.get_atoms())

    collisions = Collision_Check(model_atom_list, addition_atom_list, radius)

    if len(collisions) > 0 :
        print(len(collisions))

    if len(collisions) > collisions_accepted:
        return None #error
    else:
        return mobile_chain

def Join_Piece(model,addition,available_chain_names):
    """Return the chain "addition" object added to the model

    input:
    -model = model object containg the current model
    -addition = chain object moved acording a refernce chain superimposed
    """
    character = available_chain_names.pop()#Check before run this function if the set is empty
    addition.id = character

    model.add(addition)

    return model, character, available_chain_names

def Simulate_Model(simulation_list,relations):
    """Returns a string with the chain with less required steps expected for build a macrocomplex with all the chains without clashes

    The chain with obtain earlier all the posible chains, whas chosen as initial chian.
    if more than one chain fullfill this condition or more than one chain are the last to fill the maximum number of chains, one of them are piked at random.
    input:
    -simulation_list = list of tuples with the following structure (initial_chain,last_added_chains,total_added_chains)
    -relations = relathionship dictionary:
     -Keys = str with chain_name
     -Values = set of chains with relathionship with the key one
    """

    possible_simulations = []
    completed_simulations = set()

    for simulation in simulation_list:
        last_added_chains = "".join(list("".join("".join(relations[chains]) for chains in simulation[1])))
        new_simulation = (simulation[0],last_added_chains,simulation[2] + last_added_chains)
        if all(chain in new_simulation[2] for chain in relations.keys()):
            completed_simulations.add(new_simulation[0])
        else:
            if len(new_simulation[2]) <= len(string.ascii_letters + string.digits):
                possible_simulations.append(new_simulation)

    if len(completed_simulations) == 0:

        if len(possible_simulations) == 0:
            possible_starts = set(chain[0] for chain in simulation_list)
            return possible_starts.pop()
        else:
            return Simulate_Model(possible_simulations,relations)
    else:
        possible_starts = set(chain[0] for chain in completed_simulations)
        return possible_starts.pop()



def Chose_Start(relationships, pairs, available_chain_names):
    """Returns a starting chain name and their respective chain object with their center of mass in the (0,0,0) coordinates

    For chose a starting point, we pick the chain/s with less relathionships making the hipotesis than will be able of make the correct macrocomplex with less steps.
    if more than one chain share the condition of have less relatihionships Simulate_Model function is applyed:

    Input:
    -relationships = Relationship dictionary:
     -Keys = str with chain_name
     -Values = set of chains with relathionship with the key one
    -pairs = Chain objects dictionary:
     -Keys = interaction pair
     -Values = dictionary:
      -Keys = Chain name
      -Values = Chain object
    -available_chain_names = set with the avaiable names for the chains in the pdb format
    """

    all_chains = relationships.keys()#Not required but put here as a note

    less_related = list(key for key,val in relationships.items() if len(val) == min((len(val) for val in relationships.values())))

    if len(less_related) != 1:

        less_related_simulation = []

        for chain in less_related: #This loop format the less related chains for the simulation
            chain_simulation = (chain,chain,chain)
            less_related_simulation.append(chain_simulation)

        starting_chain = Simulate_Model(less_related_simulation,relationships)

    else:
        starting_chain = less_related[0]

    chain_object = set()

    for chains in pairs.values():
        for key,value in chains.items():
            if key == starting_chain:
                chain_object.add(value)

    starting_chain_object = chain_object.pop()
    initial_chian = cp.deepcopy(starting_chain_object)
    character = available_chain_names.pop()
    initial_chian.id = character
    initial_model = initial_chian.get_parent()
    initial_model.get_parent().id = "my_model"

    coordinates_list = []

    for residue in starting_chain_object:
        for atom in residue:
            coordinates_list.append(atom.get_coord())

    coordinates_array = np.array(coordinates_list)
    center_of_masses = np.mean(coordinates_array,axis=0,dtype=np.float64)

    for atom in initial_model.get_atoms():#center the chain in the point (0,0,0)
        new_coords = atom.get_vector()-center_of_masses
        atom.coord = new_coords.get_array()

    return tuple((initial_model,[(starting_chain, character)], available_chain_names))

def Merge_chains(candidates, model_object, available_chain_names, collisions_accepted, radius):
    """Returns all the possible combinations as a list of models, of the model and the candidates

    Input:
    -candidates = list of tuples with: (chain_object,chain_name) structure
    -model_object = model object, for join the candidates to them

    Output:
    -resulting_models = list of tuples with (model_object, (chain_name,chain_id), set(avaiable_names))

    """

    print("Merge_Chains")
    print(candidates)
    print(len(candidates))

    possible_results = set() #This become a dictionary containg the templates of the resulting models
    for number in range(len(candidates)):
        possible_results.add((number,tuple(range(len(candidates)))))#format example in the case of 4 candidates {(0,(0123))}

    for first,second in itertools.combinations(tuple(range(len(candidates))),2):

        reference_atom_list = list(candidates[first][0].get_atoms())
        mobile_atom_list = list(candidates[second][0].get_atoms())
        collisions = Collision_Check(reference_atom_list, mobile_atom_list, radius)
        if len(collisions) > collisions_accepted:#extract the collition pair from the posible results
            print(len(collisions))
            print(len(mobile_atom_list))
            print(len(reference_atom_list))

            if len(collisions) >= len(reference_atom_list):#Remove the candidate if is equal
                repeated_removed = set()
                for model in possible_results:
                    if model[0] != second:
                        repeated_removed.add((model[0],tuple(chain for chain in model[1] if chain != second)))
                        possible_results = repeated_removed

            new_possible_results = set()
            for model in possible_results:
                if model[0] == first:
                    new_possible_results.add((first,tuple(chain for chain in model[1] if chain != second)))
                elif model[1] == second:
                    new_possible_results.add((second,tuple(chain for chain in model[1] if chain != first)))
                else:
                    new_possible_results.add((model[0],tuple(chain for chain in model[1] if chain != first)))
                    new_possible_results.add((model[0],tuple(chain for chain in model[1] if chain != second)))
            possible_results = new_possible_results

    possible_results_unrepeated = set([tuple(element[1]) for element in possible_results]) #remove repeated combinations
    results_unprocesed = [set(element) for element in possible_results_unrepeated] #format for remove combinations with more possibilities
    results = cp.deepcopy(results_unprocesed)
    for result_1, result_2 in itertools.permutations(results_unprocesed,2):
        if result_1.issubset(result_2):
            if result_1 in results:
                results.remove(result_1)

    print("Possibilities finded, procesing...")
    print(results)
    print(len(results))

    resulting_models = []
    for combination in results:
        print("Combination %s"%(combination))
        if len(available_chain_names) < len(combination):
            return error #return combination and branch for example
        else:
            added_chains = []
            merged_model = cp.deepcopy(model_object)
            merged_avaiable_chain_names = cp.deepcopy(available_chain_names)
            for number in combination:
                print ("%s started"%(number))
                candidate_copied = cp.deepcopy(candidates[number][0])
                merged_model, chain_name, merged_available_chain_names = Join_Piece(merged_model, candidate_copied, merged_avaiable_chain_names)
                added_chains.append(((candidates[number][1]), chain_name))#tupple containing (chain_name,random_name_gived)

            resulting_models.append((merged_model, added_chains, merged_available_chain_names))

    print("Resulting models")
    print(len(resulting_models))

    return resulting_models #This output contains a list of tuples with (model_object,list of tuples with : (chain_name,chain_id) of the last added chains, set(avaiable_names))

def Check_Chains(model_tupled, relationships, pairs, collisions_accepted, radius):
    """Return the matching chains of one model

    Input:
    -model_tupled = tuple with (model_object, list of tuples with : (chain_name,chain_id), set(avaiable_names))
    -relationships = Relationship dictionary:
     -Keys = str with chain_name
     -Values = set of chains with relathionship with the key one
    -pairs = Chain objects dictionary:
     -Keys = interaction pair
     -Values = dictionary:
      -Keys = Chain name
      -Values = Chain object
    Output:
    -possible_additions: list of tuples with the following format: (Chain_object,chain_name)
    """

    print("Check_chains")
    possible_additions = []
    for element in model_tupled[1]:
        relations = tuple(chain for chain in relationships[element[0]])
        print (relations)
        print(len(relations))
        for chain in relations:#obtain the matching pieces
            interaction = element[0] + chain
            if not interaction in pairs:#if both orders dosn't exist
                interaction = list(pair for pair in pairs if chain in pair and element[0] in pair)[0]
            addition_tested = (Superimpose_Chain(model_tupled[0][element[1]], interaction, element[0], pairs, collisions_accepted, radius),chain)
            print(addition_tested)
            if addition_tested[0] != None:
                possible_additions.append(addition_tested)

    if len(possible_additions) == 0:
        return None
    else:
        print("output chains")
        print(len(possible_additions))
        return possible_additions


def Build_model(model_tupled, relationships, pairs, collisions_accepted = 0, radius = 7):
    """Returns a list of tuples of all the possible models taking in account the given restrictions.

    Input:
    -model_tupled = Tuple with (model_object, (chain_name,chain_id), set(avaiable_names))

    """

    print("Build_model")

    finished_models = []
    pieces_for_merge = Check_Chains(model_tupled, relationships, pairs, collisions_accepted, radius)
    if pieces_for_merge == None:
        finished_models.append(model_tupled)
    else:
        resulting_models = Merge_chains(pieces_for_merge, model_tupled[0], model_tupled[2], collisions_accepted, radius)
        for resulting_model in resulting_models:
            if len(resulting_model[2]) == 0:
                finished_models.extend(resulting_model)
            else:
                finished_models.extend(Build_model(resulting_model, relationships, pairs, collisions_accepted, radius))
    return finished_models



if __name__ == "__main__":

    print("Program start")
    settings.init()
    folder = "../example_generator/capsid_virus"

    try:
        A = pickle.load(open("relationships.p","rb"))
        B = pickle.load(open("pairs.p","rb"))
    except:
        onlyfiles = list(os.path.join(folder,f) for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)))
        A,B=Parse_List(onlyfiles)
        out_fd = open("relationships.p","wb")
        pickle.dump(A,out_fd)
        out_fd.close()
        out_fd = open("pairs.p","wb")
        pickle.dump(B,out_fd)
        out_fd.close()

    print("files_parsed")
    print(len(A.keys()))

    initial_model = Chose_Start(A,B,available_chain_names)

    models = Build_model(initial_model, A, B, 30, 2.5)

    print("write pdb")

    print(models)


    io = pdb.PDBIO()
    i = 1
    for model in models:
        io.set_structure(model[0])
        io.save("model_%s.pdb" %(i))
        i += 1



    # print(B["XA"]["A"][1]["CA"].get_coord())
    print(settings.similarity)
    print(settings.similarity)

    # print(Superimpose_Chain(B,"XA","X",B["XB"]["X"])[1]["CA"].get_coord())

    # # print(Collision_Check(B["XA"]["X"],B["XB"]["X"],8))

    # C = Join_Piece(B["XB"]["X"],B["XB"]["B"])

    # for chain in C.get_parent():
    #     print (chain)

    # print(Chose_Start(A,B))
