# -*- coding: utf-8 -*-
"""
Created on Wed Nov  6 18:09:30 2019

@author: jacqu

Utils functions for pytorch model, Rdkit and smiles format. 
"""

import numpy as np
import dgl
import torch
import pandas as pd

import rdkit
from rdkit import Chem
from rdkit.Chem import QED
from selfies import decoder
import os
import json

script_dir = os.path.dirname(os.path.realpath(__file__))


#  ============== Dumping utils  ==============


class Dumper():
    """
    Small class to deal with model loading/dumping

    Can be used as a dumping utility or a model logger
    Then it starts by adding a params.json dict (to have all necessary values) and update it with an ini and then with the
    argparse
    """

    def __init__(self, dumping_path=None, ini=None, argparse=None):
        """

        :param ini: Optional : path to ini from the root of the project
        :param argparse: Optional, an argparse object
        :param dumping_path: Optional, where to dump by params.json
        """
        self.dumping_path = dumping_path
        self.dic = self.load(
            os.path.join(script_dir, 'results/saved_models/inference_default/params.json'))

        if ini is not None:
            ini_dic = self.load(os.path.join(script_dir, '..', ini))
            self.dic.update(ini_dic)

        if argparse is not None:
            self.dic.update(argparse.__dict__)

    def dump(self, dict_to_dump=None, dumping_path=None):
        """
        Takes a dict and dumps it
        :param dict_to_dump: a python dict. If None takes own
        :param dumping_path: If None, defaults to self.dumping_path
        :return:
        """
        if dumping_path is None:
            dumping_path = self.dumping_path
        if dumping_path is None:
            raise ValueError('Where should I dump ? No dump_path provided')
        if dict_to_dump is None:
            dict_to_dump = self.dic

        j = json.dumps(dict_to_dump, indent=4)
        with open(dumping_path, 'w') as f:
            print(j, file=f)

    def load(self, file_to_read):
        with open(file_to_read, 'r') as f:
            json_dict = json.load(f)
        return json_dict


if __name__ == '__main__':
    pass
    # d = {
    #     "name": "interpolator",
    #     "children": [1, 2, 3]
    # }
    #
    # import argparse
    #
    # parser = argparse.ArgumentParser()
    # parser.add_argument('--name', type=str, default='Overriding the original dict')
    # args = parser.parse_args()
    #
    # dumper = Dumper(dumping_path='test_dump')
    # dumper.dump(d)
    # json_dict = dumper.load('test_dump')
    # print(json_dict)
    # a = json_dict['children']
    # print(a, type(a))


# ============== Dir management =====================================
def soft_mkdir(path):
    if not os.path.exists(path):
        os.mkdir(path)


def setup(name=None, permissive=True):
    """

    :param name:
    :param permissive: if False, will not allow for overwriting
    :return:
    """
    soft_mkdir(os.path.join(script_dir, 'results'))
    soft_mkdir(os.path.join(script_dir, 'results/logs'))
    soft_mkdir(os.path.join(script_dir, 'results/saved_models'))
    if name is not None:
        logdir = os.path.join(script_dir, 'results/logs', name)
        modeldir = os.path.join(script_dir, 'results/saved_models', name)
        if permissive:
            soft_mkdir(logdir)
            soft_mkdir(modeldir)
        else:
            os.mkdir(logdir)
            os.mkdir(modeldir)
    return logdir, modeldir


if __name__ == '__main__':
    pass
    # setup()
    # setup('toto')
    # setup('toto', permissive=True)
    # setup('toto', permissive=False)


# ============== Rdkit utils =====================================

def disable_rdkit_logging():
    """
    Disables RDKit logging.
    """
    import rdkit.rdBase as rkrb
    import rdkit.RDLogger as rkl
    logger = rkl.logger()
    logger.setLevel(rkl.ERROR)
    rkrb.DisableLog('rdApp.error')


def QED_oracle(smiles):
    # takes a list of smiles and returns a list of corresponding QEDs
    t = torch.zeros(len(smiles))
    for i, s in enumerate(smiles):
        m = Chem.MolFromSmiles(s)
        if (m != None):
            t[i] = QED.qed(m)
    return t


# ================= Pytorch utils ================================

def debug_memory():
    import collections, gc, torch
    tensors = collections.Counter((str(o.device), o.dtype, tuple(o.shape), o.size())
                                  for o in gc.get_objects()
                                  if torch.is_tensor(o))
    print(f"Found {len(tensors)} unique tensors. Total: {sum(tensors.values())}")
    for line in sorted(tensors.items(), key=lambda x: x[1], reverse=True):
        print('{}\t{}'.format(*line))


def send_graph_to_device(g, device):
    """
    Send dgl graph to device
    :param g: :param device:
    :return:
    """
    g.set_n_initializer(dgl.init.zero_initializer)
    g.set_e_initializer(dgl.init.zero_initializer)

    # nodes
    labels = g.node_attr_schemes()
    for l in labels.keys():
        g.ndata[l] = g.ndata.pop(l).to(device, non_blocking=True)

    # edges
    labels = g.edge_attr_schemes()
    for i, l in enumerate(labels.keys()):
        g.edata[l] = g.edata.pop(l).to(device, non_blocking=True)
    return g


# ============== Smiles handling utils ===============================

def log_reconstruction(true_idces, probas, idx_to_char, string_type='smiles'):
    """
    Input : 
        true_idces : shape (N, seq_len)
        probas : shape (N, voc_size, seq_len)
        idx_to_char : dict with idx to char mapping 
        string-type : smiles or selfies 
        
        Argmax on probas array (dim 1) to find most likely character indices 
    """
    probas = probas.to('cpu').numpy()
    true_idces = true_idces.cpu().numpy()
    N, voc_size, seq_len = probas.shape
    out_idces = np.argmax(probas, axis=1)  # get char_indices
    in_smiles, out_smiles = [], []
    for i in range(N):
        out_smiles.append(''.join([idx_to_char[idx] for idx in out_idces[i]]))
        in_smiles.append(''.join([idx_to_char[idx] for idx in true_idces[i]]))
    d = {'input smiles': in_smiles,
         'output smiles': out_smiles}

    if string_type == 'smiles':
        df = pd.DataFrame.from_dict(d)
        valid = [Chem.MolFromSmiles(o.rstrip('\n')) for o in out_smiles]
        valid = [int(m != None) for m in valid]
        frac_valid = np.mean(valid)
        return df, frac_valid
    else:
        for i in range(3):  # printing only 3 samples
            print(decoder(in_smiles[i]), ' => ', decoder(out_smiles[i]))
        return 0, 0


def log_smiles_from_indices(true_idces, out_idces, idx_to_char):
    """
    Input : 
        true_idces : shape (N, seq_len)
        out_idces : shape (N, seq_len)
        idx_to_char : dict with idx to char mapping 
    """
    N, seq_len = out_idces.shape
    if (type(true_idces) == np.ndarray):
        print('shape of true indices array: ', true_idces.shape)
        input_provided = True
    else:
        print('No input smiles given, random sampling from latent space ?')
        input_provided = False
    print('shape of output indices array: ', out_idces.shape)
    in_smiles, out_smiles = [], []
    identical = 0
    for i in range(N):
        if (input_provided):
            out_smiles.append(''.join([idx_to_char[idx] for idx in out_idces[i]]))
            in_smiles.append(''.join([idx_to_char[idx] for idx in true_idces[i]]))
            if (in_smiles == out_smiles):
                identical += 1
        else:  # Consider only valid smiles
            out = ''.join([idx_to_char[idx] for idx in out_idces[i]])
            if (Chem.MolFromSmiles(out.rstrip('\n')) != None):
                out_smiles.append(out)
    if (input_provided):
        d = {'input smiles': in_smiles,
             'output smiles': out_smiles}
        valid = [Chem.MolFromSmiles(o.rstrip('\n')) for o in out_smiles]
        valid = [int(m != None) for m in valid]
        frac_valid = np.mean(valid)
        frac_id = identical / N
    else:
        d = {'output smiles': out_smiles}
        frac_valid = len(out_smiles) / N
        frac_id = 0  # not applicable
    df = pd.DataFrame.from_dict(d)

    return df, frac_valid, frac_id


def i2s(idces, idx_to_char):
    # list of indices to sequence of characters (=smiles)
    return ''.join([idx_to_char[idx] for idx in idces])
