"""
MCMC parameter estimation using emcee
"""

import numpy as np
import emcee
from .gpscipy import GPtideScipy


def mcmc(   xd, 
            yd, 
            covfunc, 
            cov_priors,
            noise_prior,
            meanfunc=None,             
            mean_priors=[],
            mean_kwargs={},
            GPclass=GPtideScipy,
            gp_kwargs={},
            nwalkers=200, 
            nwarmup=200, 
            niter=20, 
            nprior=500,
            parallel=False,
            verbose=False):
    """
    Main MCMC function

    Run MCMC using emcee.EnsembleSampler and return posterior samples, log probability of your 
    MCMC chain, samples from your priors and the actual emcee.EnsembleSampler [for testing].

    Parameters
    ----------
    xd: numpy.ndarray [N, D]
        Input data locations / predictor variable(s)

    yd: numpy.ndarray [N,1]
        Observed data

    covfunc: function
        Covariance function

    cov_priors: list of scipy.stats.rv_continuous objects
        List containing prior probability distribution for each parameter of the covfunc
     
    noise_priors: scipy.stats.rv_continuous object       
        Prior for I.I.D. noise

    ncovparams: Zulberti - update this and redo everything

    Other Parameters
    ----------------
    meanfunc: function [None]
        Mean function 

    mean_priors: list of scipy.stats.rv_continuous objects
        List containing prior probability distribution for each parameter of the meanfunc

    mean_kwargs: dict
        Key word arguments for the mean function

    GPclass: gptide.gp.GPtide class [GPtideScipy]
        The GP class used to estimate the log marginal likelihood

    gp_kwargs: dict
        Key word arguments for the GPclass initialisation

    nwalkers: int
        see emcee.EnsembleSampler

    nwarmup: int
        see emcee.EnsembleSampler
    
    niter: int
        see emcee.EnsembleSampler.run_mcmc

    nprior: int 
        number of samples from the prior distributions to output

    parallel: bool [False]
        Set to true to run parallel

    verbose: bool [False]
        Set to true for more output

    Returns
    --------
    samples:
        MCMC chains after burn in

    log_prob:
        Log posterior probability for each sample in the MCMC chain after burn in

    p0:
        Samples from the prior distributions
    
    sampler: emcee.EnsembleSampler
        The actual emcee.EnsembleSampler used

    """
    
    if parallel:
        import os 
        os.environ["OMP_NUM_THREADS"] = "1"
        os.environ["MKL_NUM_THREADS"] = "1"
        from multiprocessing import Pool

    priors  = [noise_prior] + cov_priors + mean_priors 
    ncovparams = len(cov_priors)

    ndim = len(priors)

    p0 = [np.array([pp.rvs() for pp in priors]) for i in range(nwalkers)]
    
    if parallel:
        with Pool() as pool:

            sampler = emcee.EnsembleSampler(nwalkers, ndim, 
                                _minfunc_prior, 
                                args=(xd, yd, covfunc, meanfunc, 
                                        ncovparams, verbose, mean_kwargs, 
                                        GPclass, gp_kwargs,
                                        priors),
                                pool=pool)

            print("Running burn-in...")
            p0, _, _ = sampler.run_mcmc(p0, nwarmup, progress=True)
            sampler.reset()

            print("Running production...")
            pos, prob, state = sampler.run_mcmc(p0, niter, progress=True)
    else:
        sampler = emcee.EnsembleSampler(nwalkers, ndim, 
                                _minfunc_prior, 
                                args=(xd, yd, covfunc, meanfunc, 
                                        ncovparams, verbose, mean_kwargs, 
                                        GPclass, gp_kwargs,
                                        priors),
                                 )

        print("Running burn-in...")
        p0, _, _ = sampler.run_mcmc(p0, nwarmup, progress=True)
        sampler.reset()

        print("Running production...")
        pos, prob, state = sampler.run_mcmc(p0, niter, progress=True)
        
    
    samples = sampler.chain[:, :, :].reshape((-1, ndim))
    log_prob = sampler.get_log_prob()[:, :].reshape((-1, 1))

    # Output priors
    p0 = np.array([np.array([pp.rvs() for pp in priors]) for i in range(nprior)])
    
    return samples, log_prob, p0, sampler
 
def _minfunc_prior( params, 
                    x, 
                    Z, 
                    covfunc, 
                    meanfunc, 
                    ncovparams, 
                    verbose, 
                    mean_kwargs, 
                    GPclass, 
                    gp_kwargs,
                    priors):
    """
    This is the log_prob_fn in emcee speak. Takes a vector in the parameter space, and any additional arguments in the 
    args kwarg of the emcee.EnsembleSampler

    params:
        A sequence of parameters, 
            - The first is IID noise
            - Then there are ncovparams-1 parameters for the covfunc
            - The rest are for the meanfunc 

    """
    

    noise = params[0]                   
    covparams = params[1:ncovparams+1]   # Zulberti this terminology was confusing. Now actually the number of cov params. 
    meanparams = params[ncovparams+1:]
    
    ## Add on the priors
    log_prior = np.array([P.logpdf(val) for P, val in zip(priors, params)])
    if np.any(np.isinf(log_prior)):
        return -np.inf
    sum_prior = np.sum(log_prior)
    #sum_prior = 0.
    
    myGP = GPclass(x, x, noise, covfunc, covparams, mean_func=meanfunc,
                        mean_params=meanparams, mean_kwargs=mean_kwargs, **gp_kwargs) # Zulberti - this is initialised on every iteration. Suspect significant gains by just updating params. 
    
    logp = myGP.log_marg_likelihood(Z)  
    
    return logp + sum_prior             # Return the sume of the logs (log of the product)