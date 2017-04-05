#!/bin/bash

exit [[ "$(sha1sum $1)" ~= "$2" ]]
