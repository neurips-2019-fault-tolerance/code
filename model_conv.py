from model import *
from vis.utils.utils import apply_modifications
from keras.activations import softplus
from keras.utils import CustomObjectScope
from keras.layers import Activation, InputLayer
from keras.preprocessing import image
import numpy as np
from matplotlib import pyplot as plt
from keras import Model, Input
from tqdm import tqdm

def softplus10(x, scaler = 1.0):
    """ Softplus with variable softness """
    return softplus(x * scaler) / scaler

def replace_relu_with_softplus(model, scaler = 1.0):
  """ For a given keras model, replace all ReLU activation functions with softplus """
  print("Replacing ReLU to Softplus(%.2f)" % scaler)

  # replacing ReLU with SoftPlus10
  for i, layer in enumerate(model.layers):
    if hasattr(layer, 'activation'):
      if layer.activation.__name__ == 'relu':
        print("Replacing activation %s on layer %d/%s with softplus" % (str(layer.activation.__name__), i, str(layer)))
        layer.activation = softplus10

  # applying modifications
  print('Applying modifications...')
  with CustomObjectScope({'softplus10': softplus10}):
    model = apply_modifications(model)

  # returning the resulting model
  return model

def cut_and_flatten(model, layer):
  """ Cut a submodel from the model up to layer 'layer', sum over inputs, full model is returned is layer = -1 """
  if layer == -1: return model
  return Model(inputs = model.inputs, outputs = Dense(1, kernel_initializer = 'ones')(Flatten()(model.layers[layer].output)))

def upscale_from(model, d):
  """ Upscale image and then feed to the model as a new model """
  # new (small) input
  input_tensor = Input(shape = (d, d, 3))

  # new model taking small images and upscaling them
  n = int(model.inputs[0].shape[1])
  out = model(Lambda(lambda x : tf.image.resize_images(x, (n, n)))(input_tensor))
  model_upscale = Model(inputs = input_tensor, outputs = out)

def split_x_rc0(x, rc0 = 10):
    """ Cut first rc0 components from red channel column 0, return [cut components, rest] with rest having zeros at these places """
    # copying the cat
    x_without_first = np.copy(x)

    # taking the red channel in the first column
    x_taken = np.copy(x[:, :rc0, 0, 0])

    # removing red channel in the first column
    x_without_first[:, :rc0, 0, 0] = 0
    return x_taken, x_without_first

def merge_with_taken(model, x_without_first, rc0 = 10):
  """ Create a new model taking rc0-shaped inputs which are then merged with x_without_first from @see split_x_rc0 """
  # input with size just d
  input_tensor = InputLayer(input_shape = (rc0,))

  # side of the original image
  n = int(model.inputs[0].shape[1])

  # creating a new model
  model_upscale = Sequential()
  model_upscale.add(input_tensor)

  # adding all x but first red column
  model_upscale.add(Lambda(lambda y : tf.pad(tf.reshape(y, shape = (-1, rc0, 1, 1)),
                                           paddings = ([0, 0], [0, n - rc0], [0, n - 1], [0, 2])) + x_without_first))

  # adding the rest of VGG15
  model_upscale.add(model)

  # sanity check: when fed x_taken, will reconstruct the input correctly
  #assert np.all(K.function([model_upscale.input], [model_upscale.layers[0].output])([x_taken])[0] == x_orig), "Input is handled in a wrong way"

  return model_upscale

def load_cat(dimension = 224):
  # getting picture of a cat
  img_path = 'cat.jpg'
  img = image.load_img(img_path, target_size=(dimension, dimension))
  plt.imshow(img)
  x = image.img_to_array(img)
  x = np.expand_dims(x, axis=0)
  #x = preprocess_input(x)
  return x

def SliceLayer(to_keep):
  """ Keep only these components in the layer """
  return Lambda(lambda x : tf.gather(x, to_keep, axis = 1))

def keep_oindices(model, out_to_keep):
  """ A model with only these output indices kept """
  return Model(inputs = model.input, outputs = SliceLayer(out_to_keep)(model.output))

def compute_error_stack(exp, x, K, k):
  """ Compute error in experiment exp on input x using K repetitions and k repetitions of repetitions """
  datas = [exp.compute_error(np.array(x), repetitions = K) for _ in tqdm(range(k))]
  return np.hstack(datas)

def experiment_mean_std(exp, x, repetitions):
  """ Compute experimental mean/std for input x using number of repetitions """
  result = {}
  r = exp.compute_error(x, repetitions)
  result['mean'] = np.mean(r, axis = 1)
  result['std']  = np.std (r, axis = 1)
  return result

def predict_kept(model, x, to_keep = None):
    """ Predict knowing that the model output was modified with to_keep """
    preds = model.predict(x)
    if to_keep is not None:
        result = np.zeros(1000)
        for i, key in enumerate(to_keep):
            result[key] = preds[0][i]
        result = result.reshape(-1, 1000)
    else:
        result = preds
    return result
