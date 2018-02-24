#!/usr/bin/python3
# -*- coding: utf-8 -*-

# ============
#  To-Do FCRN
# ============
# TODO: Terminar de Portar código de treinamento
# TODO: Terminar de Portar código de validacao
# TODO: Terminar de Portar código de testes

# TODO: Segmentar Código em arquivos

# TODO: Implementar leitura das imagens pelo Tensorflow - Treinamento
# TODO: Implementar leitura das imagens pelo Tensorflow - Validação
# TODO: Implementar leitura das imagens pelo Tensorflow - Treinamento

# TODO: Implementar Mask Out dos de valores válidos

# ================
#  To-Do Monodeep
# ================
# TODO: Verificar se as tarefas abaixo ainda fazem sentido para o FCRN
# FIXME: Após uma conversa com o vitor, aparentemente tanto a saida do coarse/fine devem ser lineares, nao eh necessario apresentar o otimizar da Coarse e a rede deve prever log(depth), para isso devo converter os labels para log(y_)
# TODO: Validar Métricas.
# TODO: Adicionar mais topologias
# TODO: If detect Ctrl+C, save training state.
# TODO: Vitor sugeriu substituir a parte fully connected da rede por filtros deconvolucionais, deste modo pode-se fazer uma predicao recuperando o tamanho da imagem alem de ter muito menos parametros treinaveis na rede.


import argparse
import os
import numpy as np
import tensorflow as tf
from matplotlib import pyplot as plt
from PIL import Image
import glob
from scipy import misc as scp
from scipy import misc as scp
from skimage import exposure
from skimage import dtype_limits
from skimage import transform

import time
import warnings

import models


# ==================
#  Global Variables
# ==================
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings("ignore")  # Suppress Warnings

appName = 'fcrn'
datetime = time.strftime("%Y-%m-%d") + '_' + time.strftime("%H-%M-%S")

ENABLE_EARLY_STOP = True
SAVE_TRAINED_MODEL = True
ENABLE_TENSORBOARD = True
SAVE_TEST_DISPARITIES = True
APPLY_BILINEAR_OUTPUT = False

# Early Stop Configuration
AVG_SIZE = 20
MIN_EVALUATIONS = 1000
MAX_STEPS_AFTER_STABILIZATION = 10000
LOSS_LOG_INITIAL_VALUE = 0.1


def argumentHandler():
    # Creating Arguments Parser
    parser = argparse.ArgumentParser("Train the FCRN (Fully Convolution Residual Network) Tensorflow implementation taking image files as input.")

    # Input
    parser.add_argument('--gpu', type=str, help="Select which gpu to run the code", default='0')
    parser.add_argument('-m', '--mode', type=str, help="Select 'train' or 'test' mode", default='train')
    parser.add_argument('--model_name', type=str, help="Select Network topology: 'fcrn', etc",
                        default='fcrn')
    # parser.add_argument(    '--encoder',                   type=str,   help='type of encoder, vgg or resnet50', default='vgg')
    parser.add_argument('-i', '--data_path', type=str,
                        help="Set relative path to the input dataset <filename>.pkl file",
                        default='/media/olorin/Documentos/datasets/')

    parser.add_argument('-s', '--dataset', action='store', help="Selects the dataset ['kitti2012','kitti2015','nyudepth',kittiraw]", required=True)

    parser.add_argument('--batch_size', type=int, help="Define the Training batch size", default=16)
    parser.add_argument('--max_steps', type=int, help="Define the number of max Steps", default=1000)
    parser.add_argument('-l', '--learning_rate', type=float, help="Define the initial learning rate", default=1e-4)
    parser.add_argument('-d', '--dropout', type=float, help="Enable dropout in the model during training", default=0.5)
    parser.add_argument('--ldecay', action='store_true', help="Enable learning decay", default=False)
    parser.add_argument('-n', '--l2norm', action='store_true', help="Enable L2 Normalization", default=False)

    parser.add_argument('--full_summary', action='store_true',
                        help="If set, will keep more data for each summary. Warning: the file can become very large")

    parser.add_argument('--log_directory', type=str, help="Set directory to save checkpoints and summaries",
                        default='log_tb/')
    parser.add_argument('-r', '--restore_path', type=str, help="Set path to a specific restore to load", default='')

    parser.add_argument('-t', '--show_train_progress', action='store_true', help="Show Training Progress Images",
                        default=False)

    parser.add_argument('-v', '--show_valid_progress', action='store_true', help="Show Validation Progress Images",
                        default=False)

    parser.add_argument('-te', '--show_train_error_progress', action='store_true',
                        help="Show the first batch label, the correspondent Network predictions and the MSE evaluations.",
                        default=False)

    parser.add_argument('-o', '--output_directory', type=str,
                        help='output directory for test disparities, if empty outputs to checkpoint folder',
                        default='output/')

    parser.add_argument('-u', '--show_test_results', action='store_true', help="Show the first batch testing Network prediction img", default=False)

    return parser.parse_args()

def argumentHandler_original():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu', type=str, help="Select which gpu to run the code", default='0')
    parser.add_argument('model_path', help='Converted parameters for the model')
    parser.add_argument('image_paths', help='Directory of images to predict')
    return parser.parse_args()

def string_length_tf(t):
    return tf.py_func(len, [t], [tf.int64])


def checkArgumentsIntegrity(dataset):
    print("[fcrn/Dataloader] Selected Dataset:", dataset)

    try:
        if dataset != 'nyudepth' and dataset[0:5] != 'kitti':
            raise ValueError

    except ValueError as e:
        print(e)
        print("[Error] ValueError: '", dataset,
              "' is not a valid name! Please select one of the following datasets: "
              "'kitti<dataset_identification>' or 'nyudepth'", sep='')
        print("e.g: python3 ", os.path.splitext(sys.argv[0])[0], ".py -s kitti2012", sep='')
        raise SystemExit


def selectedDataset(DATASET_PATH_ROOT, dataset):
    dataset_path = None

    if dataset[0:5] == 'kitti':  # If the first five letters are equal to 'kitti'
        if dataset == 'kitti2012':
            dataset_path = DATASET_PATH_ROOT + 'kitti/data_stereo_flow'

        elif dataset == 'kitti2015':
            dataset_path = DATASET_PATH_ROOT + 'kitti/data_scene_flow'

        elif dataset == 'kittiraw_city':
            dataset_path = DATASET_PATH_ROOT + 'nicolas_kitti/dataset1/city/2011_09_29_drive_0071'

        elif dataset == 'kittiraw_road':
            dataset_path = DATASET_PATH_ROOT + 'nicolas_kitti/dataset1/road/2011_10_03_drive_0042'

        elif dataset == 'kittiraw_residential':
            dataset_path = DATASET_PATH_ROOT + 'nicolas_kitti/dataset1/residential/2011_09_30_drive_0028'

        elif dataset == 'kittiraw_campus':
            dataset_path = DATASET_PATH_ROOT + 'nicolas_kitti/dataset1/campus/2011_09_28_drive_0039'

        elif dataset == 'kittiraw_residential_continuous':
            # dataset_path = DATASET_PATH_ROOT + 'nicolas_kitti/dataset1/residential_continuous'                # Load from HD
            dataset_path ='/home/olorin/Documents/nicolas/mestrado_code/monodeep/data/residential_continuous' # Load from SSD


        # print(dataset_path)
        # input()
        kitti = Kitti(dataset, dataset_path)

        return kitti, dataset_path

    elif dataset == 'nyudepth':
        dataset_path = DATASET_PATH_ROOT + '/nyu-depth-v2/images'

        nyudepth = NyuDepth(dataset, dataset_path)

        return nyudepth, dataset_path


def getListFolders(path):
    return next(os.walk(path))[1]


def removeUnusedFolders(test_folders, train_folders, datasetObj, kittiOcclusion=True):
    # According to Kitti Description, occluded == All Pixels

    print("[fcrn/Dataloader] Removing unused folders for Kitti datasets...")
    unused_test_folders_idx = []
    unused_train_folders_idx = []

    if datasetObj.name == 'kitti2012':
        unused_test_folders_idx = [0, 3, 4]

        if kittiOcclusion:
            unused_train_folders_idx = [0, 2, 3, 5, 6, 7, 8, 9, 10, 11]
        else:
            unused_train_folders_idx = [0, 2, 4, 5, 6, 7, 8, 9, 10, 11]

    if datasetObj.name == 'kitti2015':
        unused_test_folders_idx = []
        if kittiOcclusion:
            unused_train_folders_idx = [0, 1, 3, 4, 5, 7, 8, 9, 10]
        else:
            unused_train_folders_idx = [1, 2, 3, 4, 5, 7, 8, 9, 10]

    if datasetObj.name[0:8] == 'kittiraw':
        unused_test_folders_idx = []
        unused_train_folders_idx = []

    test_folders = np.delete(test_folders, unused_test_folders_idx).tolist()
    train_folders = np.delete(train_folders, unused_train_folders_idx).tolist()

    # Debug
    print(test_folders)
    print(train_folders)
    print()

    return test_folders, train_folders


def getListTestFiles(folders, datasetObj):
    colors, depth = [], []

    for i in range(len(folders)):
        if datasetObj.name == 'nyudepth':
            colors = colors + glob.glob(os.path.join(datasetObj.path, 'testing', folders[i], '*_colors.png'))
            depth = depth + glob.glob(os.path.join(datasetObj.path, 'testing', folders[i], '*_depth.png'))

        elif datasetObj.name == 'kitti2012' or datasetObj.name == 'kitti2015':
            colors = colors + glob.glob(os.path.join(datasetObj.path, 'testing', folders[i], '*.png'))
            depth = []

        elif datasetObj.name[0:8] == 'kittiraw':
            if i == 1:
                colors = colors + glob.glob(os.path.join(datasetObj.path, 'testing', folders[i], '*.png'))
            if i == 0:
                depth = colors + glob.glob(os.path.join(datasetObj.path, 'testing', folders[0], '*.png'))

    # Debug
    # print("Testing")
    # print("colors:", colors)
    # print(len(colors))
    # print("depth:", depth)
    # print(len(depth))
    # print()

    return colors, depth


def getListTrainFiles(folders, datasetObj):
    colors, depth = [], []

    for i in range(len(folders)):
        if datasetObj.name == 'nyudepth':
            colors = colors + glob.glob(os.path.join(datasetObj.path, 'training', folders[i], '*_colors.png'))
            depth = depth + glob.glob(os.path.join(datasetObj.path, 'training', folders[i], '*_depth.png'))

        elif datasetObj.name == 'kitti2012':
            if i == 0:
                colors = colors + glob.glob(os.path.join(datasetObj.path, 'training', folders[i], '*.png'))
            if i == 1:
                depth = depth + glob.glob(os.path.join(datasetObj.path, 'training', folders[i], '*.png'))

        elif datasetObj.name == 'kitti2015':
            if i == 1:
                colors = colors + glob.glob(os.path.join(datasetObj.path, 'training', folders[i], '*.png'))
            if i == 0:
                depth = depth + glob.glob(os.path.join(datasetObj.path, 'training', folders[i], '*.png'))

        elif datasetObj.name[0:8] == 'kittiraw':
            if i == 1:
                colors = colors + glob.glob(os.path.join(datasetObj.path, 'training', folders[i], '*.png'))
            if i == 0:
                depth = depth + glob.glob(os.path.join(datasetObj.path, 'training', folders[i], '*.png'))

    # Debug
    # print("Training")
    # print("colors:", colors)
    # print(len(colors))
    # print("depth:", depth)
    # print(len(depth))
    # print()

    return colors, depth


def getFilesFilename(file_path_list):
    filename_list = []

    for i in range(0, len(file_path_list)):
        filename_list.append(os.path.split(file_path_list[i])[1])

    # print(filename_list)
    # print(len(filename_list))

    return filename_list


def getValidPairFiles(colors_filename, depth_filename, datasetObj):
    valid_pairs_idx = []

    colors_filename_short = []
    depth_filename_short = []

    if datasetObj.name == 'nyudepth':
        for i in range(len(colors_filename)):
            # print(colors_filename[i])
            # print(depth_filename[i])
            # print(colors_filename[i][:-11])
            # print(depth_filename[i][:-10])

            for k in range(len(colors_filename)):
                colors_filename_short.append(colors_filename[k][:-11])

            for l in range(len(depth_filename)):
                depth_filename_short.append(depth_filename[l][:-10])

            if colors_filename_short[i] in depth_filename_short:
                j = depth_filename_short.index(colors_filename_short[i])
                # print(i,j)
                valid_pairs_idx.append([i, j])

    if datasetObj.name[0:5] == 'kitti':
        for i in range(len(colors_filename)):
            if colors_filename[i] in depth_filename:
                j = depth_filename.index(colors_filename[i])

                valid_pairs_idx.append([i, j])

    # Debug
    # print("valid_pairs_idx:", valid_pairs_idx)
    # print(len(valid_pairs_idx))

    return valid_pairs_idx


def cropImage(img, x_min=None, x_max=None, y_min=None, y_max=None, size=None):
    try:
        if size is None:
            raise ValueError
    except ValueError:
        print("[ValueError] Oops! Empty cropSize list. Please sets the desired cropSize.\n")

    if len(img.shape) == 3:
        lx, ly, _ = img.shape
    else:
        lx, ly = img.shape

    # Debug
    # print("img.shape:", img.shape)
    # print("lx:",lx,"ly:",ly)

    if (x_min is None) and (x_max is None) and (y_min is None) and (y_max is None):
        # Crop
        # (y_min,x_min)----------(y_max,x_min)
        #       |                      |
        #       |                      |
        #       |                      |
        # (y_min,x_max)----------(y_max,x_max)
        x_min = round((lx - size[0]) / 2)
        x_max = round((lx + size[0]) / 2)
        y_min = round((ly - size[1]) / 2)
        y_max = round((ly + size[1]) / 2)

        crop = img[x_min: x_max, y_min: y_max]

        # Debug
        # print("x_min:",x_min,"x_max:", x_max, "y_min:",y_min,"y_max:", y_max)
        # print("crop.shape:",crop.shape)

        # TODO: Draw cropping Rectangle

    else:
        crop = img[x_min: x_max, y_min: y_max]

    return crop


def np_resizeImage(img, size):
    try:
        if size is None:
            raise ValueError
    except ValueError:
        print("[ValueError] Oops! Empty resizeSize list. Please sets the desired resizeSize.\n")

    # TODO: Qual devo usar?
    # resized = scp.imresize(img, size, interp='bilinear')  # Attention! This method doesn't maintain the original depth range!!!
    # resized = transform.resize(image=img,output_shape=size, preserve_range=True, order=0)  # 0: Nearest - neighbor
    resized = transform.resize(image=img, output_shape=size, preserve_range=True, order=1)  # 1: Bi - linear(default)

    # resized = transform.resize(image=img, output_shape=size, preserve_range=True, order=2) # 2: Bi - quadratic
    # resized = transform.resize(image=img, output_shape=size, preserve_range=True, order=3) # 3: Bi - cubic
    # resized = transform.resize(image=img, output_shape=size, preserve_range=True, order=4) # 4: Bi - quartic
    # resized = transform.resize(image=img, output_shape=size, preserve_range=True, order=5) # 5: Bi - quintic

    # Debug
    def debug():
        print(img)
        print(resized)
        plt.figure()
        plt.imshow(img)
        plt.title("img")
        plt.figure()
        plt.imshow(resized)
        plt.title("resized")
        plt.show()

    # debug()

    return resized


def normalizeImage(img):
    pixel_depth = 255

    normed = (img - pixel_depth / 2) / pixel_depth

    # Debug
    # print("img[0,0,0]:", img[0, 0, 0], "img[0,0,1]:", img[0, 0, 1], "img[0,0,2]:", img[0, 0, 2])
    # print("normed[0,0,0]:", normed[0, 0, 0], "normed[0,0,1]:", normed[0, 0, 1], "normed[0,0,2]:", normed[0, 0, 2])

    return normed


def adjust_gamma(image, gamma, gain):
    scale = float(dtype_limits(image, True)[1] - dtype_limits(image, True)[0])  # 255.0

    return ((image / scale) ** gamma) * scale * gain  # float64


def adjust_brightness(image, brightness):
    scale = float(dtype_limits(image, True)[1] - dtype_limits(image, True)[0])  # 255.0

    return ((image / scale) * brightness) * scale  # float64


# ===================
#  Class Declaration
# ===================
class Dataloader(object):
    def __init__(self, data_path, params, dataset, mode, TRAIN_VALID_RATIO=0.8):
        # 80% for Training and 20% for Validation
        checkArgumentsIntegrity(dataset)
        print("\n[fcrn/Dataloader] Description: This script prepares the ", dataset,
              ".pkl file for posterior Networks training.",
              sep='')

        # Creates Dataset Handler
        self.datasetObj, dataset_path = selectedDataset(data_path, dataset)

        # Gets the list of folders inside the 'DATASET_PATH' folder
        print('\n[fcrn/Dataloader] Getting list of folders...')
        test_folders = getListFolders(os.path.join(dataset_path, 'testing'))
        train_folders = getListFolders(os.path.join(dataset_path, 'training'))

        print("Num of folders inside '", os.path.split(dataset_path)[1], "/testing': ", len(test_folders), sep='')
        print("Num of folders inside '", os.path.split(dataset_path)[1], "/training': ", len(train_folders), sep='')
        print(test_folders, '\n', train_folders, '\n', sep='')

        # Removing unused folders for Kitti datasets
        if self.datasetObj.type == 'kitti':
            test_folders, train_folders = removeUnusedFolders(test_folders, train_folders, self.datasetObj)

        # Gets the list of files inside each folder grouping *_colors.png and *_depth.png files.
        test_files_colors_path, test_files_depth_path = getListTestFiles(test_folders, self.datasetObj)
        train_files_colors_path, train_files_depth_path = getListTrainFiles(train_folders, self.datasetObj)

        print("Summary")
        print("Num of colored images found in '", os.path.split(dataset_path)[1], "/testing/*/: ",
              len(test_files_colors_path), sep='')
        print("Num of   train_depth_filepath images found in '", os.path.split(dataset_path)[1], "/testing/*/: ",
              len(test_files_depth_path), sep='')
        print("Num of colored images found in '", os.path.split(dataset_path)[1], "/training/*/: ",
              len(train_files_colors_path), sep='')
        print("Num of   train_depth_filepath images found in '", os.path.split(dataset_path)[1], "/training/*/: ",
              len(train_files_depth_path), sep='')
        print()

        # Gets only the filename from the complete file path
        print("[fcrn/Dataloader] Getting the filename files list...")
        test_files_colors_filename = getFilesFilename(test_files_colors_path)
        test_files_depth_filename = getFilesFilename(test_files_depth_path)
        train_files_colors_filename = getFilesFilename(train_files_colors_path)
        train_files_depth_filename = getFilesFilename(train_files_depth_path)

        # Checks which files have its train_depth_filepath/disparity correspondent
        print("\n[fcrn/Dataloader] Checking which files have its train_depth_filepath/disparity correspondent...")
        test_valid_pairs_idx = getValidPairFiles(test_files_colors_filename, test_files_depth_filename, self.datasetObj)
        train_valid_pairs_idx = getValidPairFiles(train_files_colors_filename, train_files_depth_filename,
                                                  self.datasetObj)

        """Testing"""
        test_colors_filepath, test_depth_filepath = [], []
        if len(test_valid_pairs_idx):  # Some test data doesn't have depth images
            for i, val in enumerate(test_valid_pairs_idx):
                test_colors_filepath.append(test_files_colors_path[val[0]])
                test_depth_filepath.append(test_files_depth_path[val[1]])

                # print('i:', i, 'idx:', val, 'colors:', test_colors_filepath[i], '\n\t\t\t\tdepth:', test_depth_filepath[i])
        else:
            test_colors_filepath = test_files_colors_path
            test_depth_filepath = []

        self.test_dataset = test_colors_filepath
        self.test_labels = test_depth_filepath

        # Divides the Processed train data into training set and validation set
        print('\n[fcrn/Dataloader] Dividing available data into training, validation and test sets...')
        trainSize = len(train_valid_pairs_idx)
        divider = int(TRAIN_VALID_RATIO * trainSize)

        """Training"""
        train_colors_filepath, train_depth_filepath = [], []
        for i, val in enumerate(train_valid_pairs_idx):
            train_colors_filepath.append(train_files_colors_path[val[0]])
            train_depth_filepath.append(train_files_depth_path[val[1]])

            # print('i:', i, 'idx:', val, 'train_colors_filepath:', train_colors_filepath[i], '\n\t\t\ttrain_depth_filepath:', train_depth_filepath[i])

        self.train_dataset = train_colors_filepath[:divider]
        self.train_labels = train_depth_filepath[:divider]

        """Validation"""
        self.valid_dataset = train_colors_filepath[divider:]
        self.valid_labels = train_depth_filepath[divider:]

        """Final"""
        print("\nSummary")
        print("train_dataset shape:", len(self.train_dataset))
        print("train_labels shape:", len(self.train_labels))
        print("valid_dataset shape:", len(self.valid_dataset))
        print("valid_labels shape:", len(self.valid_labels))
        print("test_dataset shape:", len(self.test_dataset))
        print("test_labels shape:", len(self.test_labels))

        self.data_path = data_path
        self.params = params
        self.dataset = dataset
        self.mode = mode

        self.image_batch = None

        self.inputSize = (None, self.datasetObj.imageNetworkInputSize[0], self.datasetObj.imageNetworkInputSize[1], 3)
        self.outputSize = (None, self.datasetObj.depthNetworkOutputSize[0], self.datasetObj.depthNetworkOutputSize[1])
        self.numTrainSamples = len(self.train_dataset)
        self.numTestSamples = len(self.test_dataset)


    def readImage(self, colors_path, depth_path, mode, showImages=False):
        # The DataAugmentation Transforms should be done before the Image Normalization!!!
        # Kitti RGB Image: (375, 1242, 3) uint8     #   NyuDepth RGB Image: (480, 640, 3) uint8 #
        #     Depth Image: (375, 1242)    int32     #          Depth Image: (480, 640)    int32 #

        if mode == 'train' or mode == 'valid':
            img_colors = scp.imread(os.path.join(colors_path))
            img_depth = scp.imread(os.path.join(depth_path))

            # Data Augmentation
            img_colors_aug, img_depth_aug = self.augment_image_pair(img_colors, img_depth)

            # TODO: Implementar Random Crops
            # Crops Image
            img_colors_crop = cropImage(img_colors_aug, size=self.datasetObj.imageNetworkInputSize)
            img_depth_crop = cropImage(img_depth_aug, size=self.datasetObj.imageNetworkInputSize)

            # Normalizes RGB Image and Downsizes Depth Image
            img_colors_normed = normalizeImage(img_colors_crop)

            img_depth_downsized = np_resizeImage(img_depth_crop, size=self.datasetObj.depthNetworkOutputSize)

            # Results
            if showImages:
                def plot1():
                    scp.imshow(img_colors)
                    scp.imshow(img_depth)
                    scp.imshow(img_colors_aug)
                    scp.imshow(img_depth_aug)
                    scp.imshow(img_colors_crop)
                    scp.imshow(img_depth_crop)
                    scp.imshow(img_colors_normed)
                    scp.imshow(img_depth_downsized)

                def plot2():
                    fig, axarr = plt.subplots(4, 2)
                    axarr[0, 0].set_title("colors")
                    axarr[0, 0].imshow(img_colors)
                    axarr[0, 1].set_title("depth")
                    axarr[0, 1].imshow(img_depth)
                    axarr[1, 0].set_title("colors_aug")
                    axarr[1, 0].imshow(img_colors_aug)
                    axarr[1, 1].set_title("depth_aug")
                    axarr[1, 1].imshow(img_depth_aug)
                    axarr[2, 0].set_title("colors_crop")
                    axarr[2, 0].imshow(img_colors_crop)
                    axarr[2, 1].set_title("depth_crop")
                    axarr[2, 1].imshow(img_depth_crop)
                    axarr[3, 0].set_title("colors_normed")
                    axarr[3, 0].imshow(img_colors_normed)
                    axarr[3, 1].set_title("depth_downsized")
                    axarr[3, 1].imshow(img_depth_downsized)

                    plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=2.0)

                # plot1()
                plot2()

                plt.show()  # Display it

            # Debug
            # print(img_colors.shape, img_colors.dtype)
            # print(img_depth.shape, img_depth.dtype)
            # input()

            return img_colors_normed, img_depth_downsized, img_colors_crop, img_depth_crop

        elif mode == 'test':
            img_colors = scp.imread(os.path.join(colors_path))
            img_colors_crop = cropImage(img_colors, size=self.datasetObj.imageNetworkInputSize)
            img_colors_normed = normalizeImage(img_colors_crop)

            img_depth = None
            img_depth_crop = None
            img_depth_downsized = None
            img_depth_bilinear = None

            if depth_path is not None:
                img_depth = scp.imread(
                    os.path.join(depth_path))
                img_depth_crop = cropImage(img_depth,
                                           size=self.datasetObj.imageNetworkInputSize)  # Same cropSize as the colors image

                img_depth_downsized = np_resizeImage(img_depth_crop, size=self.datasetObj.depthNetworkOutputSize)
                img_depth_bilinear = img_depth_crop  # Copy

            return img_colors_normed, img_depth_downsized, img_colors_crop, img_depth_bilinear

    @staticmethod
    def augment_image_pair(image, depth):
        """ATTENTION! Remember to also reproduce the transforms in the depth image. However, colors transformations can DEGRADE depth information!!!"""
        # Gets `image` info
        dtype = image.dtype.type  # Needs to be <class 'numpy.uint8'>

        # Copy
        image_aug = image
        depth_aug = depth

        # Randomly flip images (Horizontally)
        do_flip = np.random.uniform(0, 1)
        if do_flip > 0.5:
            image_aug = np.flip(image, axis=1)
            depth_aug = np.flip(depth, axis=1)

        # Randomly shift gamma
        random_gamma = np.random.uniform(low=0.8, high=1.2)
        # random_gamma = 5 # Test
        image_aug = adjust_gamma(image=image_aug, gamma=random_gamma, gain=1)

        # FIXME: Not working properly
        # Randomly shift brightness
        random_brightness = np.random.uniform(0.5, 2.0)
        # random_brightness = 100
        # image_aug = adjust_brightness(image=image_aug, brightness=random_brightness)

        # Randomly shift color
        random_colors = np.random.uniform(0.8, 1.2, 3)
        white = np.ones([np.shape(image)[0], np.shape(image)[1]])
        color_image = np.stack([white * random_colors[i] for i in range(3)], axis=2)
        image_aug = np.multiply(image_aug, color_image)

        # Saturate
        image_aug = dtype(exposure.rescale_intensity(image_aug, out_range="uint8"))

        # Debug
        def debug():
            print("do_flip:", do_flip)
            print("random_gamma:", random_gamma)
            print("random_brightness:", random_brightness)
            print("random_colors:", random_colors)
            print("image - (min: %d, max: %d)" % (np.min(image), np.max(image)))
            print("image_aug - (min: %d, max: %d)" % (np.min(image_aug), np.max(image_aug)))
            # print(image.dtype, image_aug.dtype)
            print()

            def showImages():
                plt.figure(1)
                plt.imshow(image)
                plt.title("image")
                plt.figure(2)
                plt.imshow(image_aug)
                plt.title("image_aug")
                plt.pause(2)

            # scp.imshow(image)
            # scp.imshow(image_aug)
            showImages()

        # debug()

        return image_aug, depth_aug

class Kitti(object):
    def __init__(self, name, dataset_path):
        self.path = dataset_path
        self.name = name
        self.type = 'kitti'

        self.imageInputSize = [376, 1241]
        self.depthInputSize = [376, 1226]

        # Monodeep
        # self.imageNetworkInputSize = [172, 576]
        # self.depthNetworkOutputSize = [43, 144]
        # self.depthBilinearOutputSize = [172, 576]

        # FCRN
        self.imageNetworkInputSize = [228, 304]
        self.depthNetworkOutputSize = [128, 160]

        print("[fcrn/Dataloader] Kitti object created.")

def createSaveFolder():
    save_path = None
    save_restore_path = None

    if SAVE_TRAINED_MODEL or ENABLE_TENSORBOARD:
        # Saves the model variables to disk.
        relative_save_path = 'output/' + appName + '/' + datetime + '/'
        save_path = os.path.join(os.getcwd(), relative_save_path)
        save_restore_path = os.path.join(save_path, 'restore/')

        if not os.path.exists(save_restore_path):
            os.makedirs(save_restore_path)

    return save_path, save_restore_path

class Plot(object):
    def __init__(self, mode, title):
        self.fig, self.axes = None, None

        if mode == 'train':
            self.fig, self.axes = plt.subplots(4, 1)
            self.axes[0] = plt.subplot(221)
            self.axes[1] = plt.subplot(223)
            self.axes[2] = plt.subplot(222)
            self.axes[3] = plt.subplot(224)

        elif mode == 'test':
            self.fig, self.axes = plt.subplots(5, 1)
            self.axes[0] = plt.subplot(321)
            self.axes[1] = plt.subplot(323)
            self.axes[2] = plt.subplot(325)
            self.axes[3] = plt.subplot(322)
            self.axes[4] = plt.subplot(324)

        self.fig.canvas.set_window_title(title)
        self.isFirstTime = True

    # TODO: Add ColorBar
    def showTrainResults(self, raw, label, log_label, pred):
        plt.figure(1)

        # Set Titles and subplots spacing. Runs only at first Time
        if self.isFirstTime:
            self.axes[0].set_title("Raw")
            self.axes[1].set_title("Label")
            self.axes[2].set_title("log(Label)")
            self.axes[3].set_title("Pred")
            plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=1.0)

            self.isFirstTime = False

        self.axes[0].imshow(raw)
        cax1 = self.axes[1].imshow(label)
        # self.fig.colorbar(cax1)
        cax2 = self.axes[2].imshow(log_label)
        # self.fig.colorbar(cax2)
        cax3 = self.axes[3].imshow(pred)
        # self.fig.colorbar(cax3)

        plt.pause(0.001)

    def showValidResults(self, raw, label, log_label, coarse, fine):
        plt.figure(2)

        # Set Titles and subplots spacing. Runs only at first Time
        if self.isFirstTime:
            self.axes[0].set_title("Raw")
            self.axes[1].set_title("Label")
            self.axes[2].set_title("log(Label)")
            self.axes[3].set_title("Coarse")
            self.axes[4].set_title("Fine")
            plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=1.0)

            self.isFirstTime = False

        self.axes[0].imshow(raw)
        cax1 = self.axes[1].imshow(label)
        # self.fig.colorbar(cax1)
        cax2 = self.axes[2].imshow(log_label)
        # self.fig.colorbar(cax2)
        cax3 = self.axes[3].imshow(coarse)
        # self.fig.colorbar(cax3)
        cax4 = self.axes[4].imshow(fine)
        # self.fig.colorbar(cax4)

        plt.pause(0.001)


    def showTestResults(self, raw, label, log_label,coarse, fine, i):
        plt.figure(1)

        # Set Titles and subplots spacing. Runs only at first Time
        if self.isFirstTime:
            self.axes[0].set_title("Raw")
            self.axes[1].set_title("Label")
            self.axes[2].set_title("log(Label)")
            self.axes[3].set_title("Coarse")
            self.axes[4].set_title("Fine")
            plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=1.0)
            self.isFirstTime = False

        self.fig.canvas.set_window_title("Test Predictions [%d]" % i)

        self.axes[0].imshow(raw)
        cax1 = self.axes[1].imshow(label)
        # self.fig.colorbar(cax1)
        cax2 = self.axes[2].imshow(log_label)
        # self.fig.colorbar(cax2)
        cax3 = self.axes[3].imshow(coarse)
        # self.fig.colorbar(cax3)
        cax4 = self.axes[4].imshow(fine)
        # self.fig.colorbar(cax4)

        plt.pause(0.001)

    @staticmethod
    def plotTrainingProgress(raw, label, log_label, coarse, fine, figId):
        fig = plt.figure(figId)
        fig.clf()

        # fig, axes = plt.subplots(5, 1)

        ax = fig.add_subplot(3, 2, 1)
        cax = ax.imshow(raw, cmap='gray')
        plt.title("Raw")
        fig.colorbar(cax)

        ax = fig.add_subplot(3, 2, 3)
        cax = ax.imshow(label, cmap='gray')
        plt.title("Label")
        fig.colorbar(cax)

        ax = fig.add_subplot(3, 2, 5)
        cax = ax.imshow(log_label, cmap='gray')
        plt.title("log(Label)")
        fig.colorbar(cax)

        ax = fig.add_subplot(3, 2, 2)
        cax = ax.imshow(coarse, cmap='gray')
        plt.title("Coarse")
        fig.colorbar(cax)

        ax = fig.add_subplot(3, 2, 4)
        cax = ax.imshow(fine, cmap='gray')
        plt.title("Fine")
        fig.colorbar(cax)

        plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=1.0)

        fig.canvas.set_window_title("Train Predictions")

        plt.pause(0.001)

    @staticmethod
    # TODO: Add raw, log_labels, coarse
    def displayValidationProgress(label, fine, figId):
        fig = plt.figure(figId)
        fig.clf()
        ax = fig.add_subplot(2, 1, 1)
        cax = ax.imshow(label, cmap='gray')
        plt.title("valid_labels[0,:,:]")
        fig.colorbar(cax)

        ax = fig.add_subplot(2, 1, 2)
        cax = ax.imshow(fine, cmap='gray')
        plt.title("vPredictions_f[0,:,:]")
        fig.colorbar(cax)

        plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=1.0)

    @staticmethod
    def plotTrainingErrorProgress(raw, label, coarse, fine, figId):
        # Lembre que a Training Loss utilizaRMSE_log_scaleInv, porém o resultado é avaliado utilizando MSE
        coarseMSE = loss.np_MSE(y=coarse, y_=label)
        fineMSE = loss.np_MSE(y=fine, y_=label)

        fig = plt.figure(figId)
        fig.clf()

        ax = fig.add_subplot(3, 2, 1)
        cax = ax.imshow(label, cmap='gray')
        plt.title("Label")
        fig.colorbar(cax)

        # TODO: Tentar resolver o problema que a imagem rgb não era correspondente com o label
        # ax = fig.add_subplot(3, 2, 2)
        # cax = ax.imshow(batch_data_crop_img)
        # plt.title("batch_data_crop[0,:,:]")
        # fig.colorbar(cax)

        ax = fig.add_subplot(3, 2, 3)
        cax = ax.imshow(coarse, cmap='gray')
        plt.title("Coarse")
        fig.colorbar(cax)

        ax = fig.add_subplot(3, 2, 5)
        cax = ax.imshow(fine, cmap='gray')
        plt.title("Fine")
        fig.colorbar(cax)

        ax = fig.add_subplot(3, 2, 4)
        cax = ax.imshow(coarseMSE, cmap='jet')
        plt.title("MSE(Coarse)")
        fig.colorbar(cax)

        ax = fig.add_subplot(3, 2, 6)
        cax = ax.imshow(fineMSE, cmap='jet')
        plt.title("MSE(Fine)")
        fig.colorbar(cax)

        plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=1.0)

        fig = plt.gcf()  # TODO: Posso remover?
        fig.canvas.set_window_title("Train Predictions + MSE")

        plt.pause(0.001)


def predict(model_data_path, image_path):
    # Default input size
    height = 228
    width = 304
    channels = 3
    batch_size = 1

    # Read image
    img = Image.open(image_path)
    img = img.resize([width,height], Image.ANTIALIAS)
    img = np.array(img).astype('float32')
    img = np.expand_dims(np.asarray(img), axis = 0)
   
    # Create a placeholder for the input image
    input_node = tf.placeholder(tf.float32, shape=(None, height, width, channels))

    # Construct the network
    net = models.ResNet50UpProj({'data': input_node}, batch_size, 1, False)
        
    with tf.Session() as sess:

        # Load the converted parameters
        print('Loading the model')

        # Use to load from ckpt file
        saver = tf.train.Saver()     
        saver.restore(sess, model_data_path)

        # Use to load from npy file
        #net.load(model_data_path, sess) 

        # Evalute the network for the given image
        pred = sess.run(net.get_output(), feed_dict={input_node: img})
        
        # Plot result
        fig = plt.figure()
        ii = plt.imshow(pred[0,:,:,0], interpolation='nearest')
        fig.colorbar(ii)
        plt.show()
        
        return pred

# ===================== #
#  Training/Validation  #
# ===================== #
def train(args, params):
    save_path, save_restore_path = createSaveFolder()

    graph = tf.Graph()
    with graph.as_default():
        # Default input size
        batch_size = 1

        # Create a placeholder for the input image
        dataloader = Dataloader(args.data_path, params, args.dataset, args.mode)
        params['inputSize'] = dataloader.inputSize
        params['outputSize'] = dataloader.outputSize

        # print(params['inputSize'],params['outputSize'])
        tf_image = tf.placeholder(tf.float32,
                                  shape=(None, params['inputSize'][1], params['inputSize'][2], params['inputSize'][3]))

        net = models.ResNet50UpProj({'data': tf_image}, params['batch_size'], 1, False)

        # Tensorflow Variables
        tf_labels = tf.placeholder(tf.float32,
                                        shape=(None, params['outputSize'][1], params['outputSize'][2]),
                                        name='labels')  # (?, 96, 288)

        LOSS_LOG_INITIAL_VALUE = 0.1
        tf_log_labels = tf.log(tf_labels + LOSS_LOG_INITIAL_VALUE,
                                    name='log_labels')  # Just for displaying Image


        tf_global_step = tf.Variable(0, trainable=False,
                                          name='global_step')  # Count the number of steps taken.

        tf_learningRate = params['learning_rate']
        if params['ldecay']:
            tf_learningRate = tf.train.exponential_decay(tf_learningRate, tf_global_step, 1000, 0.95,
                                                              staircase=True, name='ldecay')

        def tf_MSE(tf_y, tf_log_y_):
            tf_y = tf.squeeze(tf_y, axis=3)

            loss_name = 'MSE'

            tf_npixels_valid = tf.cast(tf.size(tf_log_y_), tf.float32)  # (batchSize*height*width)

            return loss_name, (tf.reduce_sum(tf.pow(tf_log_y_ - tf_y, 2)) / tf_npixels_valid)

        loss_name, tf_loss = tf_MSE(net.get_output(), tf_log_labels)

        optimizer = tf.train.AdamOptimizer(tf_learningRate)
        train = optimizer.minimize(tf_loss, global_step=tf_global_step)

        # Creates Saver Obj
        train_saver = tf.train.Saver(tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES))


    with tf.Session(graph=graph) as sess:
        tf.global_variables_initializer().run()

        # =================
        #  Training Loop
        # =================
        start = time.time()

        if args.show_train_progress:
            train_plotObj = Plot(args.mode, title='Train Predictions')

        if args.show_valid_progress:
            valid_plotObj = Plot(args.mode, title='Validation Prediction')


        batch_data = np.zeros((args.batch_size,
                               params['inputSize'][1],
                               params['inputSize'][2],
                               params['inputSize'][3]),
                              dtype=np.float64)  # (?, 172, 576, 3)

        batch_data_crop = np.zeros((args.batch_size,
                                    params['inputSize'][1],
                                    params['inputSize'][2],
                                    params['inputSize'][3]),
                                   dtype=np.uint8)  # (?, 172, 576, 3)

        batch_labels = np.zeros((args.batch_size,
                                 params['outputSize'][1],
                                 params['outputSize'][2]),
                                dtype=np.int32)  # (?, 43, 144)


        for step in range(args.max_steps):
            start2 = time.time()

            # Training and Validation Batches and Feed Dictionary Preparation
            offset = (step * args.batch_size) % (dataloader.numTrainSamples - args.batch_size)  # Pointer
            batch_data_path = dataloader.train_dataset[offset:(offset + args.batch_size)]
            batch_labels_path = dataloader.train_labels[offset:(offset + args.batch_size)]

            for i in range(len(batch_data_path)):
                # FIXME: os tipos retornados das variaveis estao errados, quando originalmente eram uint8 e int32, lembrar que o placeholder no tensorflow é float32
                image, depth, image_crop, _ = dataloader.readImage(batch_data_path[i],
                                                                   batch_labels_path[i],
                                                                   mode='train',
                                                                   showImages=False)

                # print(image.dtype,depth.dtype, image_crop.dtype, depth_crop.dtype)

                batch_data[i] = image
                batch_labels[i] = depth
                batch_data_crop[i] = image_crop

            feed_dict_train = {tf_image: batch_data, tf_labels: batch_labels}

            # ----- Session Run! ----- #
            _, log_labels, train_pred, train_loss = sess.run([train, tf_log_labels, net.get_output(), tf_loss], feed_dict=feed_dict_train)  # Training
            valid_loss = -1 # FIXME: value
            # -----

            # Prints Training Progress
            if step % 10 == 0:
                if args.show_train_progress:
                    train_plotObj.showTrainResults(raw=batch_data_crop[0, :, :], label=batch_labels[0, :, :],
                                                   log_label=log_labels[0, :, :],
                                                   pred=train_pred[0, :, :, 0])

                    # Plot.plotTrainingProgress(raw=batch_data_crop[0, :, :], label=batch_labels[0, :, :],log_label=log_labels[0, :, :], coarse=train_PredCoarse[0, :, :],fine=train_PredFine[0, :, :], fig_id=3)
                    pass

                if args.show_train_error_progress:
                    # FIXME:
                    # Plot.plotTrainingErrorProgress(raw=batch_data_crop[0, :, :], label=batch_labels[0, :, :],
                    #                                coarse=train_PredCoarse[0, :, :], fine=train_PredFine[0, :, :],
                    #                                figId=8)
                    pass

                if args.show_valid_progress:
                    # FIXME:
                    # valid_plotObj.showValidResults(raw=valid_data_crop_o[0, :, :, :], label=valid_labels_o[0],
                    #                                log_label=np.log(valid_labels_o[0] + LOSS_LOG_INITIAL_VALUE),
                    #                                coarse=valid_PredCoarse[0], fine=valid_PredFine[0])
                    pass

                end2 = time.time()
                print('step: {0:d}/{1:d} | t: {2:f} | Batch trLoss: {3:>16.4f} | vLoss: {4:>16.4f} '.format(step,
                                                                                                            args.max_steps,
                                                                                                            end2 - start2,
                                                                                                            train_loss,
                                                                                                            valid_loss))

        end = time.time()
        sim_train = end - start
        print("\n[Network/Training] Training FINISHED! Time elapsed: %f s\n" % sim_train)

        # ==============
        #  Save Results
        # ==============
        if SAVE_TRAINED_MODEL:
            def saveTrainedModel(save_path, session, saver, model_name):
                """ Saves trained model """
                # Creates saver obj which backups all the variables.
                print("[Network/Training] List of Saved Variables:")
                for i in tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES):
                    print(i)  # i.name if you want just a name

                file_path = saver.save(session, os.path.join(save_path, "model." + model_name))
                print("\n[Results] Model saved in file: %s" % file_path)

            saveTrainedModel(save_restore_path, sess, train_saver, args.model_name)

        # Pegar a função do bitboyslab que está mais completa
        # Logs the obtained test result
        f = open('results.txt', 'a')
        f.write("%s\t\t%s\t\t%s\t\t%s\t\tsteps: %d\ttrain_lossF: %f\tvalid_lossF: %f\t%f\n" % (
            datetime, args.model_name, args.dataset, loss_name, step, train_loss, valid_loss, sim_train))
        f.close()


# ========= #
#  Testing  #
# ========= #
def test(args, params):
    print('[%s] Selected mode: Test' % appName)
    print('[%s] Selected Params: %s' % (appName, args))

    # TODO: fazer rotina para pegar imagens externas, nao somente do dataset
    # -----------------------------------------
    #  Network Testing Model - Importing Graph
    # -----------------------------------------
    # Loads the dataset and restores a specified trained model.
    dataloader = Dataloader(args.data_path, params, args.dataset, args.mode)
    model = ImportGraph(args.restore_path)

    # Memory Allocation
    # Length of test_dataset used, so when there is not test_labels, the variable will still be declared.
    predCoarse = np.zeros((dataloader.numTestSamples, dataloader.outputSize[1], dataloader.outputSize[2]),
                          dtype=np.float32)  # (?, 43, 144)

    predFine = np.zeros((dataloader.numTestSamples, dataloader.outputSize[1], dataloader.outputSize[2]),
                        dtype=np.float32)  # (?, 43, 144)

    test_labels_o = np.zeros((len(dataloader.test_dataset), dataloader.outputSize[1], dataloader.outputSize[2]),
                             dtype=np.int32)  # (?, 43, 144)

    test_data_o = np.zeros(
        (len(dataloader.test_dataset), dataloader.inputSize[1], dataloader.inputSize[2], dataloader.inputSize[3]),
        dtype=np.uint8)  # (?, 172, 576, 3)

    test_data_crop_o = np.zeros(
        (len(dataloader.test_dataset), dataloader.inputSize[1], dataloader.inputSize[2], dataloader.inputSize[3]),
        dtype=np.uint8)  # (?, 172, 576, 3)

    predCoarseBilinear = np.zeros((dataloader.numTestSamples, dataloader.inputSize[1], dataloader.inputSize[2]),
                                  dtype=np.float32)  # (?, 172, 576)

    predFineBilinear = np.zeros((dataloader.numTestSamples, dataloader.inputSize[1], dataloader.inputSize[2]),
                                dtype=np.float32)  # (?, 172, 576)

    # TODO: Usar?
    # test_labelsBilinear_o = np.zeros(
    #     (len(dataloader.test_dataset), dataloader.inputSize[1], dataloader.inputSize[2]),
    #     dtype=np.int32)  # (?, 172, 576)

    # ==============
    #  Testing Loop
    # ==============
    start = time.time()
    for i, image_path in enumerate(dataloader.test_dataset):
        start2 = time.time()

        if dataloader.test_labels:  # It's not empty
            image, depth, image_crop, depth_bilinear = dataloader.readImage(dataloader.test_dataset[i],
                                                                            dataloader.test_labels[i],
                                                                            mode='test')

            test_labels_o[i] = depth
            # test_labelsBilinear_o[i] = depth_bilinear # TODO: Usar?
        else:
            image, _, image_crop, _ = dataloader.readImage(dataloader.test_dataset[i], None, mode='test')

        test_data_o[i] = image
        test_data_crop_o[i] = image_crop

        if APPLY_BILINEAR_OUTPUT:
            predCoarse[i], predFine[i], predCoarseBilinear[i], predFineBilinear[i] = model.networkPredict(image,
                                                                                                          APPLY_BILINEAR_OUTPUT)
        else:
            predCoarse[i], predFine[i] = model.networkPredict(image)

        # Prints Testing Progress
        end2 = time.time()
        print('step: %d/%d | t: %f' % (i + 1, dataloader.numTestSamples, end2 - start2))
        # break # Test

    # Testing Finished.
    end = time.time()
    print("\n[Network/Testing] Testing FINISHED! Time elapsed: %f s" % (end - start))

    # ==============
    #  Save Results
    # ==============
    # Saves the Test Predictions
    print("[Network/Testing] Saving testing predictions...")
    if args.output_directory == '':
        output_directory = os.path.dirname(args.restore_path)
    else:
        output_directory = args.output_directory

    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    if SAVE_TEST_DISPARITIES:
        np.save(output_directory + 'test_coarse_disparities.npy', predCoarse)
        np.save(output_directory + 'test_fine_disparities.npy', predFine)

    # Calculate Metrics
    if dataloader.test_labels:
        metrics.evaluateTesting(predFine, test_labels_o)
    else:
        print(
            "[Network/Testing] It's not possible to calculate Metrics. There are no corresponding labels for Testing Predictions!")

    # Show Results
    if args.show_test_results:
        test_plotObj = Plot(args.mode, title='Test Predictions')
        for i in range(dataloader.numTestSamples):
            test_plotObj.showTestResults(test_data_crop_o[i], test_labels_o[i], np.log(test_labels_o[i] + LOSS_LOG_INITIAL_VALUE), predCoarse[i], predFine[i], i)


def main():
    # Parse arguments
    args = argumentHandler()
    # args = argumentHandler_original()

    os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu

    # Predict the image
    # pred = predict(args.model_path, args.image_paths)

    modelParams = {'inputSize': -1,
              'outputSize': -1,
              'model_name': args.model_name,
              'learning_rate': args.learning_rate,
              'batch_size': args.batch_size,
              'max_steps': args.max_steps,
              'dropout': args.dropout,
              'ldecay': args.ldecay,
              'l2norm': args.l2norm,
              'full_summary': args.full_summary}

    if args.mode == 'train':
        train(args, modelParams)
    elif args.mode == 'test':
        test(args, modelParams)

    print("\n[%s] Done." % appName)

    os._exit(0)

if __name__ == '__main__':
    main()

        



