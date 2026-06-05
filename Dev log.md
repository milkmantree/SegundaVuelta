# Dev Log

## To-Do

### getInfoDistritos

1. ~~Agregar el otro endpoint.~~
2. ~~Hacer la consulta a los dos endpoints o definir como ERROR (todo o NADA).~~
3. ~~Editar la estructura de datos que se guarda.~~
4. ~~Lograr que se pueda correr en multiples instancias.~~

### processData

1. ~~Procesar los datos en un formato ordenado.~~
2. ~~Calcular tablas agregadas.~~
3. ~~Calcular variables relevantes para la estimación.~~
4. ~~Calcular votos habiles maximos por ubigeo.~~

### estimation

1. ~~Defnir metodología de estimación de propagacion~~
2. ~~Definir la metodología de estimación por migración de votos.~~
3. ~~Crear el codigo de estimación con información base la información aggregada~~

### diseño de visualización

1. ~~Evaluar si es necesario crear una pequeña pagina web en la que se muestren los resultados actuales y las estimaciones de los modelos.~~
2. ~~Editar el front end del modelo de migración para que tambien muestre las proporciones con base votos validos y no totales. Además eliminar el tag 2da vuelta en la tabla, para el que vive en segunda vuelta (aca es redundante).~~

### debugging and details


1. ~~Generate a view where I can see the proyected results for both methodologies with point estimator and confidence intervals for each department.~~
2. ~~Rethink the way the detailed predictions for both models per department is shown. I would prefer an additional tab with the details of obsrveed, predicted and confidence interval per department column, all from ambito extranjero should be in a dropdown list different to the Peru ambito. Also, show the model details, specifically transfer coefficients and other department level estimation details with a pop up per department that opens when you click the name.~~
2. ~~Generate and populate a historical file with each refresh of prediction and add a graph in the front end that shows the series of how predictions have been evolving. This must include confidence intervals.Add this to the front end. ~~

### Final piping

1. Figure out a way that the results update every 30 minutes.
2. Figure how to host the results page.

### Día de las elecciones

1. Revisar que en el GET de `/resumen-general/totales/` estes capturando correctamente la participación ciudadana. e no ser el caso, no podrás inferir el número de votos habiles correcto, ni el número de votos habiles por estimar. Esto afecta el archivo `scraper.py`.