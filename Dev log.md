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
2. Definir la metodología de estimación por migración de votos.
3. Crear el codigo de estimación con información base la información aggregada
4. 

### diseño de visualización

1. Evaluar si es necesario crear una pequeña pagina web en la que se muestren los resultados actuales y las estimaciones de los modelos.


### Día de las elecciones

1. Revisar que en el GET de `/resumen-general/totales/` estes capturando correctamente la participación ciudadana. e no ser el caso, no podrás inferir el número de votos habiles correcto, ni el número de votos habiles por estimar. Esto afecta el archivo `scraper.py` 