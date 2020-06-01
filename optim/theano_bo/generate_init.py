# -*- coding: utf-8 -*-
"""
Created on Sun Feb  9 15:13:46 2020

@author: jacqu

Load trained model and use it to embed molecules from their SMILES. 


Reconstruction, validity and novelty metrics 


"""

import sys
import os
import numpy as np
import pandas as pd
import torch
import argparse
import pickle

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.realpath(__file__))
    sys.path.append(os.path.join(script_dir, '../..'))

from rdkit import Chem
from rdkit.Chem import MolFromSmiles, MolToSmiles
from rdkit.Chem import AllChem

from selfies import decoder

if __name__ == '__main__':
    from dataloaders.molDataset import  Loader
    from model import  model_from_json
    from data_processing.comp_metrics import cycle_score, logP, qed
    from data_processing.sascorer import calculateScore

    parser = argparse.ArgumentParser()

    parser.add_argument('-i', '--input', help="path to csv containing molecules", type=str, default='data/250k_zinc.csv')
    
    parser.add_argument('--obj', help="BO objective", type=str, default='logp')
    
    parser.add_argument('-n', "--cutoff", help="Number of molecules to embed. -1 for all", type=int, default=2000)
    
    parser.add_argument('-name', '--name', type=str, default='250k') 

    # =====================
    
    alphabet = '250k_alphabets.json'
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    args, _ = parser.parse_known_args()

    # Load model (on gpu if available)
    model = model_from_json(args.name)
    model.to(device)
    model.eval()

    # Load dataframe with mols to embed
    path = os.path.join(script_dir, '../..', args.input)
    if args.cutoff > 0:
        smiles_df = pd.read_csv(path, index_col=0, nrows=args.cutoff)  # cutoff csv at nrows
    else:
        smiles_df = pd.read_csv(path, index_col=0)

    # Initialize dataloader with empty dataset
    dataloader = Loader(props=[], 
                    targets=[], 
                    csv_path = None,
                    maps_path = '../../map_files',
                    alphabet_name = alphabet,
                    vocab='selfies', 
                    num_workers = 0,
                    test_only=True)

    # embed molecules in latent space of dimension 64
    print('>>> Start computation of molecules embeddings...')
    z = model.embed(dataloader, smiles_df)  # z has shape (N_molecules, latent_size)

    # Save molecules latent embeds to pickle.
    savedir = os.path.join(script_dir, '../..', 'data/latent_features_and_targets')
    np.savetxt(os.path.join(savedir, 'latent_features.txt'), z)
    print(f'>>> Saved latent representations of {z.shape[0]} molecules to ~/data/latent_features.txt')

    # Compute properties : 
    smiles_rdkit = smiles_df.smiles
    
    if args.obj =='logp':
    
        print(f'>>> Computing clogP for {len(smiles_rdkit)} mols')
        
        logP_values = []
        SA_scores = []
        cycle_scores = []
        
        for i in range(len(smiles_rdkit)):
            
            m=MolFromSmiles(smiles_rdkit[ i ] )
            logP_values.append(logP(m))
            SA_scores.append(-calculateScore(m))
            cycle_scores.append(-cycle_score(m))
            
            if i % 10000==0:
                print(i)
        
        SA_scores_normalized = (np.array(SA_scores) - np.mean(SA_scores)) / np.std(SA_scores)
        logP_values_normalized = (np.array(logP_values) - np.mean(logP_values)) / np.std(logP_values)
        cycle_scores_normalized = (np.array(cycle_scores) - np.mean(cycle_scores)) / np.std(cycle_scores)
    
        targets = SA_scores_normalized + logP_values_normalized + cycle_scores_normalized
        
        print('>>> Saving targets and split scores to .txt files')
        np.savetxt(os.path.join(savedir, 'targets_logp.txt'), targets)
        np.savetxt(os.path.join(savedir, 'logP_values.txt'), np.array(logP_values))
        np.savetxt(os.path.join(savedir, 'SA_scores.txt'), np.array(SA_scores))
        np.savetxt(os.path.join(savedir, 'cycle_scores.txt'), np.array(cycle_scores))
        print('done!')
        
    elif args.obj == 'qed':
        
        print(f'>>> Computing cQED for {len(smiles_rdkit)} mols')
        
        qed_values = []
        SA_scores = []
        cycle_scores = []
        
        for i in range(len(smiles_rdkit)):
            
            m=MolFromSmiles(smiles_rdkit[ i ] )
            qed_values.append(qed(m))
            SA_scores.append(-calculateScore(m))
            cycle_scores.append(-cycle_score(m))
            
            if i % 10000==0:
                print(i)
        
        SA_scores_normalized = (np.array(SA_scores) - np.mean(SA_scores)) / np.std(SA_scores)
        qed_values_normalized = (np.array(qed_values) - np.mean(qed_values)) / np.std(qed_values)
        cycle_scores_normalized = (np.array(cycle_scores) - np.mean(cycle_scores)) / np.std(cycle_scores)
    
        targets = SA_scores_normalized + qed_values_normalized + cycle_scores_normalized
        
        print('>>> Saving targets and split scores to .txt files')
        np.savetxt(os.path.join(savedir, 'targets_qed.txt'), targets)
        np.savetxt(os.path.join(savedir, 'qed_values.txt'), np.array(qed_values))
        np.savetxt(os.path.join(savedir, 'SA_scores.txt'), np.array(SA_scores))
        np.savetxt(os.path.join(savedir, 'cycle_scores.txt'), np.array(cycle_scores))
        print('done!')
        
    elif args.obj == 'qsar':
        
        print(f'>>> Computing QSAR for {len(smiles_rdkit)} mols')
        
        with open(os.path.join(script_dir, '../..', 'results/qsar_svm.pickle'), 'rb') as f :
            clf = pickle.load(f)
            print('-> Loaded qsar svm')
            
        fps=[]
        for s in smiles_rdkit:
            m = Chem.MolFromSmiles(s)
            fps.append(np.array(AllChem.GetMorganFingerprintAsBitVect(m , 3, nBits=2048)).reshape(1,-1))
        fps = np.vstack(fps)
        targets = clf.predict_proba(fps)[:,1]
        
        targets = (targets -np.mean(targets)) /np.std(targets)
        
        print('>>> Saving QSAR targets to .txt file')
        np.savetxt(os.path.join(savedir, 'targets_qsar.txt'), targets)

        print('done!')
        
    elif args.obj == 'docking':
        
        print(f'>>> Computing docking scores for {len(smiles_rdkit)} mols (!! time)')
        
        raise NotImplementedError
        
        