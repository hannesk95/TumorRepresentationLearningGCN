import numpy as np
from glob import glob
import torch.utils.data
import torch
import os
import torchio as tio
from sklearn.utils.class_weight import compute_class_weight
from sklearn.model_selection import train_test_split
from sklearn.utils import shuffle


class SingleImgDataset3D(torch.utils.data.Dataset):

    def __init__(self, dataset, mode, cnn_name, split=-1, tta=False):

        assert mode in ['train', 'val', 'test']

        self.mode = mode
        self.split = split
        self.dataset = dataset
        self.test_time_augmentation = tta

        if self.dataset == 'NSCLC':
            all_filepaths = glob('/media/johannes/WD Elements/NSCLC_Stefan/median_resampled+max_cropped/*image.pt')
            all_labels = glob('/media/johannes/WD Elements/NSCLC_Stefan/labels/*')
            all_labels_ids = [label.split('/')[-1].split('_')[0] for label in all_labels]

            files = sorted([file for file in all_filepaths if file.split('/')[-1].split('_')[0] in all_labels_ids])
            # files_new = [file for file in files if "LUNG1" in file.split("/")[-1]]
            # files = files_new
            files_ids = [file.split('/')[-1].split('_')[0] for file in files]

            labels = sorted([label for label in all_labels if label.split('/')[-1].split('_')[0] in files_ids])
            labels_binary = [0 if 'adeno' in label else 1 if 'squamous' in label else np.nan for label in labels]

            self.train_imgs, self.val_imgs, self.labels_train, self.labels_val = train_test_split(files, labels_binary, train_size=0.6,
                                                                                                  random_state=42, stratify=labels_binary)

            self.val_imgs, self.test_imgs, self.labels_val, self.labels_test = train_test_split(self.val_imgs, self.labels_val, test_size=0.5,
                                                                                                random_state=42, stratify=self.labels_val)

            # test_val_images = self.test_imgs + self.val_imgs
            # test_val_labels = self.labels_test + self.labels_val

            # self.test_imgs, self.labels_test = shuffle(test_val_images, test_val_labels, random_state=42)

        elif self.dataset == 'RADCURE':
            self.filepaths = sorted(glob('/home/johannes/Desktop/MICCAI24/data/RADCURE/volume+seg/*crimgnew.pt'))
            self.labelpaths = sorted(glob('/home/johannes/Desktop/MICCAI24/data/RADCURE/volume+seg/*label*.pt'))

            train_ids = torch.load('/home/johannes/Desktop/MICCAI24/data/RADCURE/X_train_RADCURE_split.pt')
            val_ids = torch.load('/home/johannes/Desktop/MICCAI24/data/RADCURE/X_val_RADCURE_split.pt')
            test_ids = torch.load('/home/johannes/Desktop/MICCAI24/data/RADCURE/X_test_RADCURE_split.pt')

            # val_test = val_ids + test_ids
            # np.random.shuffle(val_test,)
            # half_size = int(len(val_test)/2)
            # val_ids = val_test[:half_size]
            # test_ids = val_test[half_size:]

            self.train_imgs = [path for path in self.filepaths if path.split('/')[-1].split('_')[0] in train_ids]
            self.val_imgs = [path for path in self.filepaths if path.split('/')[-1].split('_')[0] in val_ids]
            self.test_imgs = [path for path in self.filepaths if path.split('/')[-1].split('_')[0] in test_ids]

            # if self.mode == "val":
            #     if self.split == 0:
            #         self.val_imgs = self.val_imgs[:60]
            #     elif self.split == 1:
            #         self.val_imgs = self.val_imgs[60:120]
            #     else:
            #         self.val_imgs = self.val_imgs[120:]

            self.train_labels = [path for path in self.labelpaths if path.split('/')[-1].split('_')[0] in train_ids]
            self.val_labels = [path for path in self.labelpaths if path.split('/')[-1].split('_')[0] in val_ids]
            self.test_labels = [path for path in self.labelpaths if path.split('/')[-1].split('_')[0] in test_ids]

            self.labels_train = [0 if 'negative' in path else 1 for path in self.train_labels]
            self.labels_val = [0 if 'negative' in path else 1 for path in self.val_labels]
            self.labels_test = [0 if 'negative' in path else 1 for path in self.test_labels]

        if self.mode == 'train':
            self.filepaths = self.train_imgs
        elif self.mode == 'val':
            self.filepaths = self.val_imgs
        else:
            self.filepaths = self.test_imgs

        self.class_weights = torch.tensor(compute_class_weight(class_weight='balanced', classes=np.unique(self.labels_train), y=self.labels_train)).to(torch.float32).cuda()

        if cnn_name in ['ResNet50-3D', 'ResNet101-3D']:

            self.preprocess = tio.transforms.Compose([
                tio.transforms.Clamp(-1000, 1000),
                tio.transforms.Resize(224),
                tio.transforms.ZNormalization()])

            self.augment = tio.transforms.Compose([
                tio.transforms.RandomAffine(scales=0.05, degrees=10, translation=20),
                tio.transforms.RandomFlip(axes=(0, 1, 2))])

        elif cnn_name == 'ResNet18-3D':

            self.preprocess = tio.transforms.Compose([
                tio.transforms.Clamp(-1000, 1000),
                tio.transforms.ZNormalization()])

            self.augment = tio.transforms.Compose([
                tio.transforms.RandomAffine(scales=0.0, degrees=0.0, translation=20),
                tio.transforms.RandomFlip(axes=(0, 1, 2))])

    def __len__(self):

        if self.mode == 'train':
            return len(self.train_imgs)
        elif self.mode == 'val':
            return len(self.val_imgs)
        else:
            return len(self.test_imgs)

    def __getitem__(self, idx):

        if self.mode == 'train':
            images = self.train_imgs
            labels = self.labels_train
        elif self.mode == 'val':
            images = self.val_imgs
            labels = self.labels_val
        elif self.mode == 'test':
            images = self.test_imgs
            labels = self.labels_test

        path = images[idx]
        img = torch.load(path).unsqueeze(dim=0).to(torch.float32)
        label = torch.tensor(labels[idx]).to(torch.long)

        if self.mode == 'train':
            # img = self.clip(img)
            # img = torch.clamp(img, -1000, 1000)
            # img = self.normalize(img)
            img = self.preprocess(img)
            img = self.augment(img)

        else:
            # img = self.clip(img)
            # img = torch.clamp(img, -1000, 1000)
            # img = self.normalize(img)
            img = self.preprocess(img)

            if self.test_time_augmentation:
                img = self.augment(img)

        return (label, img, path)

    def normalize(self, volume):
        return (volume - torch.mean(volume)) / torch.std(volume)

    def clip(self, volume):
        min_value = torch.quantile(volume, 0.05)
        max_value = torch.quantile(volume, 0.95)
        return torch.clamp(volume, min=min_value, max=max_value)

class AugmentationDataset3D(torch.utils.data.Dataset):
    def __init__(self, path, mode, n_augmentations):

        self.mode = mode
        self.n_augmentations = n_augmentations

        train_feature_paths = sorted(glob(os.path.join(path, 'train_features*.pt')))[:n_augmentations]
        val_feature_paths = sorted(glob(os.path.join(path, 'val_features*.pt')))[:n_augmentations]
        test_feature_paths = sorted(glob(os.path.join(path, 'test_features*.pt')))[:n_augmentations]

        train_data = [torch.load(path).unsqueeze(0) for path in train_feature_paths]
        val_data = [torch.load(path).unsqueeze(0) for path in val_feature_paths]
        test_data = [torch.load(path).unsqueeze(0) for path in test_feature_paths]

        self.train_data = torch.concat(train_data, dim=0).to(torch.float32)
        self.val_data = torch.concat(val_data, dim=0).to(torch.float32)
        self.test_data = torch.concat(test_data, dim=0).to(torch.float32)

        self.train_labels = torch.load(os.path.join(path, 'train_labels.pt')).to(torch.long)
        self.val_labels = torch.load(os.path.join(path, 'val_labels.pt')).to(torch.long)
        self.test_labels = torch.load(os.path.join(path, 'test_labels.pt')).to(torch.long)

        self.class_weights = torch.tensor(compute_class_weight(class_weight='balanced',
                                                               classes=np.unique(self.train_labels.numpy()),
                                                               y=self.train_labels.numpy())).to(torch.float32).cuda()


        if self.mode == 'train':
            self.filepaths = self.train_data
        elif self.mode == 'val':
            self.filepaths = self.val_data
        else:
            self.filepaths = self.test_data

    def __len__(self):
        if self.mode == 'train':
            return self.train_data.shape[1]
        elif self.mode == 'val':
            return self.val_data.shape[1]
        else:
            return self.test_data.shape[1]

    def __getitem__(self, idx):

        if self.mode == 'train':
            data = self.train_data
            labels = self.train_labels
        elif self.mode == 'val':
            data = self.val_data
            labels = self.val_labels
        elif self.mode == 'test':
            data = self.test_data
            labels = self.test_labels

        patient_data = data[:, idx, :].to(torch.float32)
        patient_label = labels[idx].to(torch.float32)

        return patient_label, patient_data


class MultiviewImgDataset3D(torch.utils.data.Dataset):
    def __init__(self, dataset, mode, n_augmentations, flips, translations):

        assert mode in ['train', 'val', 'test']

        self.mode = mode
        self.dataset = dataset
        self.n_augmentations = n_augmentations

        if self.dataset == 'NSCLC':
            all_filepaths = glob('/media/johannes/WD Elements/NSCLC_Stefan/median_resampled+max_cropped/*image.pt')
            all_labels = glob('/media/johannes/WD Elements/NSCLC_Stefan/labels/*')
            all_labels_ids = [label.split('/')[-1].split('_')[0] for label in all_labels]

            files = sorted([file for file in all_filepaths if file.split('/')[-1].split('_')[0] in all_labels_ids])
            # files_new = [file for file in files if "LUNG1" in file.split("/")[-1]]
            # files = files_new
            files_ids = [file.split('/')[-1].split('_')[0] for file in files]

            labels = sorted([label for label in all_labels if label.split('/')[-1].split('_')[0] in files_ids])
            labels_binary = [0 if 'adeno' in label else 1 if 'squamous' in label else np.nan for label in labels]

            self.train_imgs, self.val_imgs, self.labels_train, self.labels_val = train_test_split(files, labels_binary, train_size=0.6,
                                                                                                  random_state=42, stratify=labels_binary)

            self.val_imgs, self.test_imgs, self.labels_val, self.labels_test = train_test_split(self.val_imgs, self.labels_val, test_size=0.5,
                                                                                                random_state=42, stratify=self.labels_val)

            # test_val_images = self.test_imgs + self.val_imgs
            # test_val_labels = self.labels_test + self.labels_val

            # self.test_imgs, self.labels_test = shuffle(test_val_images, test_val_labels, random_state=42)


        else:
            self.filepaths = sorted(glob('/home/johannes/Desktop/MICCAI24/data/RADCURE/volume+seg/*crimgnew.pt'))
            self.labelpaths = sorted(glob('/home/johannes/Desktop/MICCAI24/data/RADCURE/volume+seg/*label*.pt'))

            train_ids = torch.load('/home/johannes/Desktop/MICCAI24/data/RADCURE/X_train_RADCURE_split.pt')
            val_ids = torch.load('/home/johannes/Desktop/MICCAI24/data/RADCURE/X_val_RADCURE_split.pt')
            test_ids = torch.load('/home/johannes/Desktop/MICCAI24/data/RADCURE/X_test_RADCURE_split.pt')

            val_test = val_ids + test_ids
            np.random.shuffle(val_test,)
            half_size = int(len(val_test)/2)
            val_ids = val_test[:half_size]
            test_ids = val_test[half_size:]

            self.train_imgs = [path for path in self.filepaths if path.split('/')[-1].split('_')[0] in train_ids]
            self.val_imgs = [path for path in self.filepaths if path.split('/')[-1].split('_')[0] in val_ids]
            self.test_imgs = [path for path in self.filepaths if path.split('/')[-1].split('_')[0] in test_ids]

            self.train_labels = [path for path in self.labelpaths if path.split('/')[-1].split('_')[0] in train_ids]
            self.val_labels = [path for path in self.labelpaths if path.split('/')[-1].split('_')[0] in val_ids]
            self.test_labels = [path for path in self.labelpaths if path.split('/')[-1].split('_')[0] in test_ids]

            self.labels_train = [0 if 'negative' in path else 1 for path in self.train_labels]
            self.labels_val = [0 if 'negative' in path else 1 for path in self.val_labels]
            self.labels_test = [0 if 'negative' in path else 1 for path in self.test_labels]

        if self.mode == 'train':
            self.filepaths = self.train_imgs
        elif self.mode == 'val':
            self.filepaths = self.val_imgs
        else:
            self.filepaths = self.test_imgs

        self.class_weights = torch.tensor(compute_class_weight(class_weight='balanced', classes=np.unique(self.labels_train), y=self.labels_train)).to(torch.float32).cuda()

        self.preprocess = tio.transforms.Compose([
            tio.transforms.Clamp(-1000, 1000),
            tio.transforms.ZNormalization()
        ])

        # self.augment = tio.transforms.RandomAffine(scales=0.0, translation=0.0, degrees=180.0)

        self.augmentations = []
        # scales = np.random.uniform(0.95, 1.05, n_augmentations)
        # degrees = np.random.uniform(-10, 10, n_augmentations)
        # translations = np.random.uniform(-20, 20, n_augmentations)
        for i in range(n_augmentations):
            self.augmentations.append(tio.transforms.Compose([
                                        tio.transforms.RandomAffine(scales=(0, 0), degrees=(0, 0), translation=(translations[i], translations[i])),
                                        tio.transforms.RandomFlip(axes=(int(flips[i])), flip_probability=1.0)]))

        # self.augment = tio.transforms.RandomAffine(scales=0.05, degrees=10, translation=20)


    def __len__(self):
        if self.mode == 'train':
            return len(self.train_imgs)
        elif self.mode == 'val':
            return len(self.val_imgs)
        else:
            return len(self.test_imgs)

    def __getitem__(self, idx):

        if self.mode == 'train':
            images = self.train_imgs
            labels = self.labels_train
        elif self.mode == 'val':
            images = self.val_imgs
            labels = self.labels_val
        else:
            images = self.test_imgs
            labels = self.labels_test

        path = images[idx]
        img = torch.load(path).unsqueeze(dim=0)
        label = torch.tensor(labels[idx]).to(torch.long)

        img_augmentations = []
        for i in range(self.n_augmentations):
            img_augmentations.append(self.augmentations[i](img))

        img_augmentations = torch.concatenate(img_augmentations)

        return label, img_augmentations
