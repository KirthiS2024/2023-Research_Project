# -*- coding: utf-8 -*-
"""Original GW200115_042309.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/11ZOLgmqnNwnEMcXCU8Vdj44woYb3pWXi

### Make sure PyCBC is installed
"""

import sys
!{sys.executable} -m pip install pycbc --no-cache-dir
# we'll also need the ptemcee and epsie samplers, which are not installed by default
!{sys.executable} -m pip install "emcee==2.2.1" ptemcee epsie

"""The imports we'll need for this notebook:"""

import numpy
from matplotlib import pyplot
import logging

import pycbc
pycbc.init_logging(True)
from pycbc.inference import models
from pycbc.inference.models import BaseModel

class Foo(BaseModel):
    pass

try:
    foo = Foo()
except TypeError as e:
    print(e)
    pass

from scipy import stats

class TestPoisson(BaseModel):
    """A model with a Poisson distribution for the likelihood."""
    name = 'test_poisson'

    def _loglikelihood(self):
        # get the current parameters;
        # they should have a mu and a counts
        params = self.current_params
        try:
            mu = params['mu']
            kk = int(params['k'])
        except KeyError:
            raise ValueError("must provide a mu and a k")
        return stats.poisson.logpmf(kk, mu)

"""Now let's register the model with PyCBC:"""

from pycbc.inference.models import register_model

register_model(TestPoisson)

config = """
[model]
name = test_poisson

[variable_params]
k =

[static_params]
mu = 3

[prior-k]
name = uniform
min-k = 0
max-k = 20

[sampler]
name = epsie
nchains = 10
ntemps = 1
niterations = 1000

[jump_proposal-k]
name = bounded_discrete
min-k = ${prior-k|min-k}
max-k = ${prior-k|max-k}

[sampler-burn_in]
burn-in-test = halfchain
"""

with open('poisson.ini', 'w') as fp:
    print(config, file=fp)

from pycbc.workflow import WorkflowConfigParser
from pycbc.inference import models

cp = WorkflowConfigParser(['poisson.ini'])

model = models.read_from_config(cp)

"""Let's test that the model works by evaluating a single point:"""

model.update(k=2)

model.loglikelihood

"""Now we'll setup the sampler and sample the parameter space, writing out to `possoin.hdf`:"""

import os
from pycbc.inference.sampler import load_from_config as load_sampler_from_config

sampler = load_sampler_from_config(cp, model, output_file='poisson.hdf')
sampler.run()
sampler.finalize()
os.rename(sampler.checkpoint_file, 'poisson.hdf')
os.remove(sampler.backup_file)

"""Now let's plot it with `plot_posterior`:"""

!pycbc_inference_plot_posterior \
    --input-file poisson.hdf \
    --output-file posterior-possion.png \
    --plot-marginal --verbose

from IPython.display import Image
Image('posterior-possion.png', width=640)

"""## 2. Model with data from GWOSC

### The model:
"""

class PoissonBurst(BaseModel):
    """A model in which the noise model is Poissonian and the signal model
    is an exponentially decaying burst.
    """
    name = 'poisson_burst'

    def __init__(self, times, counts, variable_params, **kwargs):
        super().__init__(variable_params, **kwargs)
        # store the data
        self.times = times
        self.counts = counts

    def _loglikelihood(self):
        params = self.current_params
        # the signal model
        amp = params['amp']
        tau = params['tau']
        t0 = params['t0']
        finalmass = params['finalmass']
        mass1 = params['mass1']
        mass2 = params['mass2']
        # generate the signal
        times = self.times
        signal = self.get_signal(times, amp, tau, t0, finalmass, mass1, mass2)
        # subtract the signal from the observed data
        residual = self.counts - signal
        # make sure the residual is positive
        residual[residual < 0] = 0
        # the noise model parameters
        mu = params['mu']

        # the loglikelihood is the sum over the time series
        return stats.poisson.logpmf(residual, mu).sum()

    @staticmethod
    def get_signal(times, amp, tau, t0, finalmass, mass1, mass2):
        """Generate the signal model.

        Having a function like this isn't required for the model;
        the signal could just be generated within the ``_loglikelihood``
        function. We break it out to a separate function here to
        make it easier to generate a simulated signal.
        """
        signal = numpy.zeros(len(times))
        mask = times >= t0
        signal[mask] = (amp*numpy.exp(-(times[mask]-t0)/tau)).astype(int)
        return signal

    @classmethod
    def from_config(cls, cp, **kwargs):
        """Loads the counts data in addition to the standard parameters.

        This requires a [data] section to exist in the config file that
        points to a text file containing the times and counts; example:

            [data]
            counts-data = /path/to/txt
        """
        # get the data
        datafn = cp.get('data', 'counts-data')
        data = numpy.loadtxt(datafn)
        times = data[:,0]
        counts = data[:,1]
        args = {'times': times, 'counts': counts}
        args.update(kwargs)
        return super().from_config(cp, **args)

# register the model
register_model(PoissonBurst)

"""Now we'll generate a simulated signal and noise and save it."""

# set a seed to make this reproducible
numpy.random.seed(10)

duration = 32
times = numpy.arange(duration)
# noise parameters
mu = 4
mass1 = 5.9
mass2 = 1.44
# generate some fake noise
noise = stats.poisson.rvs(mu, size=duration)

# simulated signal properties
t0 = duration/4
# we'll make the signal be a 10 sigma
# deviation from the noise
amp = 10 * mu**0.5 + mu
tau = duration/8
finalmass = (mass1 + mass2)/2
print('Signal parameters:')
print('amp: {}, tau: {}, t0: {}'.format(amp, tau, t0))
signal = PoissonBurst.get_signal(times, amp, tau, t0, finalmass, mass1, mass2)

# the "observed" data
data = signal + noise
# save the data to a file
numpy.savetxt('simulated_data.txt', numpy.vstack((times, data)).T)

"""Here's what the simulated noise and signal look like:"""

fig, ax = pyplot.subplots()
ax.step(times, data, c='black', lw=2.5, label='Data')
ax.step(times, noise, ls='--', lw=2, label='Noise')
ax.step(times, signal, ls='--', lw=2, label='Signal')
ax.set_xlabel('time')
ax.set_ylabel('counts')
ax.legend()
fig.show()

"""Now lets setup our configuration file to analyze it:"""

config = """
[model]
name = poisson_burst

[data]
counts-data = simulated_data.txt

[variable_params]
amp =
tau =
finalmass =

[static_params]
# we'll fix the noise parameters
mu = 4
t0 = 8
mass1 = 5.9
mass2 = 1.4

[prior-amp]
name = uniform
min-amp = 10
max-amp = 30

[prior-tau]
name = uniform
min-tau = 1
max-tau = 10

[prior-finalmass]
name = uniform
min-finalmass = 5.5
max-finalmass = 9.0

[sampler]
# this time we'll use the emcee sampler
name = emcee
nwalkers = 100
niterations = 4000

[sampler-burn_in]
burn-in-test = halfchain
"""

with open('poisson_burst.ini', 'w') as fp:
    print(config, file=fp)

"""Now we'll load the config file and do the inference:"""

cp = WorkflowConfigParser(['poisson_burst.ini'])
model = models.read_from_config(cp)

sampler = load_sampler_from_config(cp, model,
                                   output_file='poisson_burst.hdf')
sampler.run()
sampler.finalize()
os.rename(sampler.checkpoint_file, 'poisson_burst.hdf')
os.remove(sampler.backup_file)

"""Let's plot the resulting posterior:"""

!pycbc_inference_plot_posterior \
    --input-file poisson_burst.hdf \
    --output-file posterior-possion_burst.png \
    --plot-marginal --plot-scatter --z-arg loglikelihood \
    --plot-contours --max-kde-samples 5000 \
    --expected-parameters amp:{amp} tau:{tau} \
    --verbose

Image('posterior-possion_burst.png', width=640)